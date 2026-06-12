/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import (
	"context"
	"fmt"
	"sort"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/tools/events"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	jarvisv1alpha1 "github.com/jonasgovaerts/jarvis/operator/api/v1alpha1"
	jarvisevents "github.com/jonasgovaerts/jarvis/operator/internal/events"
	"github.com/jonasgovaerts/jarvis/operator/internal/forge"
	"github.com/jonasgovaerts/jarvis/operator/internal/jobs"
)

const (
	defaultTTLAfterFinished = 30 * 24 * time.Hour
	stillRunningRequeue     = 30 * time.Second
	suspendedRequeue        = 5 * time.Minute
	concurrencyGateRequeue  = 2 * time.Minute
	awaitingMergeRequeue    = time.Minute
	maxCIFixAttempts        = 2
)

// retryBackoff returns the wait before re-spawning a failed stage attempt.
func retryBackoff(attempt int32) time.Duration {
	switch {
	case attempt <= 1:
		return time.Minute
	case attempt == 2:
		return 5 * time.Minute
	default:
		return 15 * time.Minute
	}
}

// WorkItemReconciler drives a WorkItem through the agent pipeline:
//
//	Pending → Analyzing → Developing → AwaitingCI → AwaitingMerge → RolloutCheck → Succeeded
//
// Only this controller writes WorkItem status; agents report results through
// Job termination messages (internal/jobs.Envelope).
type WorkItemReconciler struct {
	client.Client
	Scheme   *runtime.Scheme
	Recorder events.EventRecorder
	// Events publishes to NATS JetStream; nil disables publishing (envtest).
	Events jarvisevents.Publisher
}

// +kubebuilder:rbac:groups=jarvis.dev,resources=workitems,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=jarvis.dev,resources=workitems/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=jarvis.dev,resources=workitems/finalizers,verbs=update
// +kubebuilder:rbac:groups=jarvis.dev,resources=managedrepositories,verbs=get;list;watch
// +kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch;create;delete
// +kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

func (r *WorkItemReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	wi := &jarvisv1alpha1.WorkItem{}
	if err := r.Get(ctx, req.NamespacedName, wi); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}
	// orig is the server state every status patch diffs against.
	orig := wi.DeepCopy()

	// Deletion: owned Jobs/ConfigMaps are garbage-collected via owner refs;
	// the finalizer exists so terminal events can be published (step 7).
	if !wi.DeletionTimestamp.IsZero() {
		if controllerutil.ContainsFinalizer(wi, jarvisv1alpha1.WorkItemFinalizer) {
			controllerutil.RemoveFinalizer(wi, jarvisv1alpha1.WorkItemFinalizer)
			if err := r.Update(ctx, wi); err != nil {
				return ctrl.Result{}, err
			}
		}
		return ctrl.Result{}, nil
	}

	if !controllerutil.ContainsFinalizer(wi, jarvisv1alpha1.WorkItemFinalizer) {
		controllerutil.AddFinalizer(wi, jarvisv1alpha1.WorkItemFinalizer)
		if err := r.Update(ctx, wi); err != nil {
			return ctrl.Result{}, err
		}
	}

	if wi.Status.Phase.IsTerminal() {
		return r.reconcileTerminal(ctx, wi)
	}

	repo := &jarvisv1alpha1.ManagedRepository{}
	repoKey := client.ObjectKey{Namespace: wi.Namespace, Name: wi.Spec.RepositoryRef.Name}
	if err := r.Get(ctx, repoKey, repo); err != nil {
		if apierrors.IsNotFound(err) {
			log.Info("referenced ManagedRepository missing", "repo", repoKey.Name)
			return r.fail(ctx, orig, wi, "RepositoryMissing",
				fmt.Sprintf("ManagedRepository %q not found", repoKey.Name))
		}
		return ctrl.Result{}, err
	}

	// Keep the repository label in sync for cheap label-based queries.
	if wi.Labels[jarvisv1alpha1.LabelRepository] != repo.Name {
		if wi.Labels == nil {
			wi.Labels = map[string]string{}
		}
		wi.Labels[jarvisv1alpha1.LabelRepository] = repo.Name
		wi.Labels[jarvisv1alpha1.LabelSourceType] = string(wi.Spec.Source.Type)
		if err := r.Update(ctx, wi); err != nil {
			return ctrl.Result{}, err
		}
	}

	suspended := wi.Spec.Suspend || repo.Spec.Suspend

	switch wi.Status.Phase {
	case "":
		return r.initialize(ctx, orig, wi)

	case jarvisv1alpha1.PhasePending:
		if suspended {
			return ctrl.Result{RequeueAfter: suspendedRequeue}, nil
		}
		return r.reconcilePending(ctx, orig, wi, repo)

	case jarvisv1alpha1.PhaseAnalyzing:
		return r.reconcileStage(ctx, orig, wi, repo, jarvisv1alpha1.StageAnalyzer, suspended, r.onAnalyzed)

	case jarvisv1alpha1.PhaseDeveloping:
		return r.reconcileStage(ctx, orig, wi, repo, jarvisv1alpha1.StageDeveloper, suspended, r.onDeveloped)

	case jarvisv1alpha1.PhaseAwaitingCI:
		return r.reconcileStage(ctx, orig, wi, repo, jarvisv1alpha1.StageDevOps, suspended, r.onCIChecked)

	case jarvisv1alpha1.PhaseAwaitingMerge:
		return r.reconcileAwaitingMerge(ctx, orig, wi, repo)

	case jarvisv1alpha1.PhaseRolloutCheck:
		if repo.Spec.GitOps == nil {
			return r.completeWithoutRollout(ctx, orig, wi)
		}
		return r.reconcileStage(ctx, orig, wi, repo, jarvisv1alpha1.StageSRE, suspended, r.onRolloutDecided)
	}

	return ctrl.Result{}, nil
}

// initialize moves a fresh WorkItem into Pending.
func (r *WorkItemReconciler) initialize(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem) (ctrl.Result, error) {
	wi.Status.Phase = jarvisv1alpha1.PhasePending
	wi.Status.StartedAt = ptrTime(metav1.Now())
	wi.Status.ObservedGeneration = wi.Generation
	if err := r.Status().Patch(ctx, wi, client.MergeFrom(orig)); err != nil {
		return ctrl.Result{}, err
	}
	r.Recorder.Eventf(wi, nil, corev1.EventTypeNormal, "Created", "Reconcile", "WorkItem accepted into the pipeline")
	r.publish(ctx, wi, jarvisevents.SubjectCreated, string(wi.UID)+":created", jarvisevents.WorkflowCreated{
		Name:       wi.Name,
		Namespace:  wi.Namespace,
		Repository: repoLabel(wi),
		SourceType: string(wi.Spec.Source.Type),
		Title:      wi.Spec.Source.TitleText(),
	})
	return ctrl.Result{Requeue: true}, nil
}

// reconcilePending applies the per-repository concurrency gate (oldest first).
func (r *WorkItemReconciler) reconcilePending(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository) (ctrl.Result, error) {
	var list jarvisv1alpha1.WorkItemList
	if err := r.List(ctx, &list, client.InNamespace(wi.Namespace),
		client.MatchingLabels{jarvisv1alpha1.LabelRepository: repo.Name}); err != nil {
		return ctrl.Result{}, err
	}

	maxConcurrent := repo.Spec.Pipeline.MaxConcurrentWorkItems
	if maxConcurrent <= 0 {
		maxConcurrent = 2
	}

	active := int32(0)
	var pending []jarvisv1alpha1.WorkItem
	for _, item := range list.Items {
		switch {
		case item.Status.Phase.IsTerminal() || item.Status.Phase == "":
		case item.Status.Phase == jarvisv1alpha1.PhasePending:
			pending = append(pending, item)
		default:
			active++
		}
	}
	if active >= maxConcurrent {
		return ctrl.Result{RequeueAfter: concurrencyGateRequeue}, nil
	}

	sort.Slice(pending, func(i, j int) bool {
		return pending[i].CreationTimestamp.Before(&pending[j].CreationTimestamp)
	})
	slots := maxConcurrent - active
	eligible := false
	for i := range pending {
		if int32(i) >= slots {
			break
		}
		if pending[i].Name == wi.Name {
			eligible = true
			break
		}
	}
	if !eligible {
		return ctrl.Result{RequeueAfter: concurrencyGateRequeue}, nil
	}

	return r.transition(ctx, orig, wi, jarvisv1alpha1.PhaseAnalyzing, "starting analysis")
}

// stageSuccessFn folds a successful envelope into status and returns the next phase.
type stageSuccessFn func(wi *jarvisv1alpha1.WorkItem, env *jobs.Envelope) (jarvisv1alpha1.WorkItemPhase, string, error)

// reconcileStage runs the ensure-Job / read-result / retry loop for one stage.
func (r *WorkItemReconciler) reconcileStage(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository, stage jarvisv1alpha1.AgentStage, suspended bool, onSuccess stageSuccessFn) (ctrl.Result, error) {
	log := logf.FromContext(ctx)
	phase := string(wi.Status.Phase)
	attempt := wi.Status.Retries[phase]

	job := &batchv1.Job{}
	jobKey := client.ObjectKey{Namespace: wi.Namespace, Name: jobs.JobName(wi, stage, attempt)}
	err := r.Get(ctx, jobKey, job)

	switch {
	case apierrors.IsNotFound(err):
		if suspended {
			return ctrl.Result{RequeueAfter: suspendedRequeue}, nil
		}
		job = jobs.Build(wi, repo, stage, attempt)
		if err := controllerutil.SetControllerReference(wi, job, r.Scheme); err != nil {
			return ctrl.Result{}, err
		}
		if err := r.Create(ctx, job); err != nil {
			return ctrl.Result{}, err
		}
		log.Info("spawned agent job", "job", job.Name, "stage", stage, "attempt", attempt)
		r.Recorder.Eventf(wi, nil, corev1.EventTypeNormal, "AgentStarted", "Reconcile", "%s attempt %d (job %s)", stage, attempt, job.Name)

		wi.Status.ActiveJob = &corev1.ObjectReference{
			Kind: "Job", Namespace: job.Namespace, Name: job.Name, APIVersion: "batch/v1",
		}
		return ctrl.Result{}, r.Status().Patch(ctx, wi, client.MergeFrom(orig))

	case err != nil:
		return ctrl.Result{}, err
	}

	complete, failed := jobFinished(job)
	if !complete && !failed {
		return ctrl.Result{RequeueAfter: stillRunningRequeue}, nil
	}

	message, msgErr := r.terminationMessage(ctx, job)
	var env *jobs.Envelope
	var parseErr error
	if msgErr == nil && message != "" {
		env, parseErr = jobs.ParseEnvelope(message)
	}

	switch {
	case env != nil && env.Succeeded():
		next, note, err := onSuccess(wi, env)
		if err != nil {
			// Malformed result payload from the agent: a rerun won't fix it.
			return r.fail(ctx, orig, wi, "ResultInvalid", err.Error())
		}
		return r.transition(ctx, orig, wi, next, note)

	case env != nil:
		return r.handleStageFailure(ctx, orig, wi, repo, stage, env.Error.Reason, env.Error.Message, env.Error.Retryable)

	default:
		// No parseable envelope: infra-style failure (eviction, deadline,
		// crash). Retryable by definition.
		reason, msg := "JobFailed", "agent job finished without a readable envelope"
		if parseErr != nil {
			msg = parseErr.Error()
		}
		if cond := findJobCondition(job, batchv1.JobFailed); cond != nil && cond.Reason != "" {
			reason = cond.Reason
		}
		return r.handleStageFailure(ctx, orig, wi, repo, stage, reason, msg, true)
	}
}

// handleStageFailure applies retry-with-backoff semantics, or fails the item.
func (r *WorkItemReconciler) handleStageFailure(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository, stage jarvisv1alpha1.AgentStage, reason, message string, retryable bool) (ctrl.Result, error) {
	phase := string(wi.Status.Phase)
	attempt := wi.Status.Retries[phase]

	maxRetries := int32(jobs.DefaultMaxRetries)
	if cfg, ok := repo.Spec.Pipeline.Agents[stage]; ok && cfg.MaxRetries != nil {
		maxRetries = *cfg.MaxRetries
	}

	if retryable && attempt < maxRetries {
		if wi.Status.Retries == nil {
			wi.Status.Retries = map[string]int32{}
		}
		wi.Status.Retries[phase] = attempt + 1
		wi.Status.ActiveJob = nil
		if err := r.Status().Patch(ctx, wi, client.MergeFrom(orig)); err != nil {
			return ctrl.Result{}, err
		}
		r.Recorder.Eventf(wi, nil, corev1.EventTypeWarning, "AgentRetry", "Reconcile",
			"%s failed (%s: %s); retry %d/%d", stage, reason, message, attempt+1, maxRetries)
		return ctrl.Result{RequeueAfter: retryBackoff(attempt + 1)}, nil
	}

	return r.fail(ctx, orig, wi, reason, message)
}

// --- stage success handlers --------------------------------------------------

func (r *WorkItemReconciler) onAnalyzed(wi *jarvisv1alpha1.WorkItem, env *jobs.Envelope) (jarvisv1alpha1.WorkItemPhase, string, error) {
	var res jarvisv1alpha1.AnalysisResult
	if err := env.DecodeResult(&res); err != nil {
		return "", "", err
	}
	if ref, ok := env.Artifacts["report"]; ok {
		res.ReportRef = ref
	}
	wi.Status.Analysis = &res
	setCond(wi, jarvisv1alpha1.CondAnalyzed, metav1.ConditionTrue, res.Verdict, res.Summary)

	switch res.Verdict {
	case "CodeChange":
		return jarvisv1alpha1.PhaseDeveloping, "analysis: code change required", nil
	case "Misconfiguration":
		return jarvisv1alpha1.PhaseRolloutCheck, "analysis: misconfiguration — skipping development", nil
	case "NotActionable":
		return jarvisv1alpha1.PhaseSkipped, "analysis: not actionable", nil
	default:
		return "", "", fmt.Errorf("unknown analysis verdict %q", res.Verdict)
	}
}

func (r *WorkItemReconciler) onDeveloped(wi *jarvisv1alpha1.WorkItem, env *jobs.Envelope) (jarvisv1alpha1.WorkItemPhase, string, error) {
	var res jarvisv1alpha1.DevelopmentResult
	if err := env.DecodeResult(&res); err != nil {
		return "", "", err
	}
	wi.Status.Development = &res
	setCond(wi, jarvisv1alpha1.CondPRCreated, metav1.ConditionTrue, "PROpened", res.PRURL)
	return jarvisv1alpha1.PhaseAwaitingCI, "PR opened, watching CI", nil
}

func (r *WorkItemReconciler) onCIChecked(wi *jarvisv1alpha1.WorkItem, env *jobs.Envelope) (jarvisv1alpha1.WorkItemPhase, string, error) {
	var res jarvisv1alpha1.CIResult
	if err := env.DecodeResult(&res); err != nil {
		return "", "", err
	}
	wi.Status.CI = &res

	switch res.Status {
	case "Passed":
		setCond(wi, jarvisv1alpha1.CondCIPassed, metav1.ConditionTrue, "ChecksGreen", res.CheckSuiteURL)
		if res.Merged {
			setCond(wi, jarvisv1alpha1.CondMerged, metav1.ConditionTrue, "Merged", res.MergeSHA)
			return jarvisv1alpha1.PhaseRolloutCheck, "PR merged, checking rollout", nil
		}
		return jarvisv1alpha1.PhaseAwaitingMerge, "CI green, awaiting human merge", nil

	case "Failed":
		setCond(wi, jarvisv1alpha1.CondCIPassed, metav1.ConditionFalse, "ChecksFailed", res.FailureAnalysis)
		if wi.Status.CIFixAttempts < maxCIFixAttempts {
			wi.Status.CIFixAttempts++
			// Bump both stage attempt counters so fix-loop Jobs get fresh names.
			if wi.Status.Retries == nil {
				wi.Status.Retries = map[string]int32{}
			}
			wi.Status.Retries[string(jarvisv1alpha1.PhaseDeveloping)]++
			wi.Status.Retries[string(jarvisv1alpha1.PhaseAwaitingCI)]++
			return jarvisv1alpha1.PhaseDeveloping,
				fmt.Sprintf("CI failed, fix loop %d/%d", wi.Status.CIFixAttempts, maxCIFixAttempts), nil
		}
		return "", "", fmt.Errorf("CI failed after %d fix attempts: %s", maxCIFixAttempts, res.FailureAnalysis)

	case "TimedOut":
		return "", "", fmt.Errorf("CI polling timed out: %s", res.FailureAnalysis)

	default:
		return "", "", fmt.Errorf("unknown CI status %q", res.Status)
	}
}

func (r *WorkItemReconciler) onRolloutDecided(wi *jarvisv1alpha1.WorkItem, env *jobs.Envelope) (jarvisv1alpha1.WorkItemPhase, string, error) {
	var res jarvisv1alpha1.RolloutResult
	if err := env.DecodeResult(&res); err != nil {
		return "", "", err
	}
	wi.Status.Rollout = &res
	setCond(wi, jarvisv1alpha1.CondRolloutDecided, metav1.ConditionTrue, res.Decision, res.Reason)
	return jarvisv1alpha1.PhaseSucceeded, "pipeline complete", nil
}

// --- non-stage phases ----------------------------------------------------------

// reconcileAwaitingMerge waits for the PR to merge: either the devops agent
// already merged it (autoMerge) or a human merges and the forge poll sees it.
func (r *WorkItemReconciler) reconcileAwaitingMerge(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository) (ctrl.Result, error) {
	if wi.Status.CI != nil && wi.Status.CI.Merged {
		setCond(wi, jarvisv1alpha1.CondMerged, metav1.ConditionTrue, "Merged", wi.Status.CI.MergeSHA)
		return r.transition(ctx, orig, wi, jarvisv1alpha1.PhaseRolloutCheck, "PR merged, checking rollout")
	}

	if wi.Status.Development != nil && repo.Spec.Provider == "github" {
		merged, mergeSHA, err := r.pollMergeState(ctx, wi, repo)
		if err != nil {
			logf.FromContext(ctx).Error(err, "merge-state poll failed")
			return ctrl.Result{RequeueAfter: awaitingMergeRequeue}, nil
		}
		if merged {
			if wi.Status.CI == nil {
				wi.Status.CI = &jarvisv1alpha1.CIResult{Status: "Passed"}
			}
			wi.Status.CI.Merged = true
			wi.Status.CI.MergeSHA = mergeSHA
			setCond(wi, jarvisv1alpha1.CondMerged, metav1.ConditionTrue, "Merged", mergeSHA)
			return r.transition(ctx, orig, wi, jarvisv1alpha1.PhaseRolloutCheck, "PR merged, checking rollout")
		}
	}
	return ctrl.Result{RequeueAfter: awaitingMergeRequeue}, nil
}

// pollMergeState asks the forge whether the PR merged, using the repository token.
func (r *WorkItemReconciler) pollMergeState(ctx context.Context, wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository) (bool, string, error) {
	secret := &corev1.Secret{}
	key := client.ObjectKey{Namespace: repo.Namespace, Name: repo.Spec.CredentialsSecretRef.Name}
	if err := r.Get(ctx, key, secret); err != nil {
		return false, "", err
	}
	token := string(secret.Data["token"])
	return forge.PRMergeState(ctx, token, repo.Spec.Owner, repo.Spec.Name, wi.Status.Development.PRNumber)
}

// completeWithoutRollout finishes items whose repository has no GitOps mapping.
func (r *WorkItemReconciler) completeWithoutRollout(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem) (ctrl.Result, error) {
	wi.Status.Rollout = &jarvisv1alpha1.RolloutResult{
		Decision: "NotRequired",
		Reason:   "repository has no gitops mapping",
	}
	setCond(wi, jarvisv1alpha1.CondRolloutDecided, metav1.ConditionTrue, "NotRequired", "no gitops mapping")
	return r.transition(ctx, orig, wi, jarvisv1alpha1.PhaseSucceeded, "pipeline complete (no rollout)")
}

// reconcileTerminal applies the post-completion TTL.
func (r *WorkItemReconciler) reconcileTerminal(ctx context.Context, wi *jarvisv1alpha1.WorkItem) (ctrl.Result, error) {
	if wi.Status.CompletedAt == nil {
		return ctrl.Result{}, nil
	}
	ttl := defaultTTLAfterFinished
	if wi.Spec.TTLSecondsAfterFinished != nil {
		ttl = time.Duration(*wi.Spec.TTLSecondsAfterFinished) * time.Second
	}
	expiry := wi.Status.CompletedAt.Add(ttl)
	if time.Now().After(expiry) {
		return ctrl.Result{}, client.IgnoreNotFound(r.Delete(ctx, wi))
	}
	return ctrl.Result{RequeueAfter: time.Until(expiry)}, nil
}

// --- helpers --------------------------------------------------------------------

// transition patches all accumulated status mutations plus the phase change.
func (r *WorkItemReconciler) transition(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem, next jarvisv1alpha1.WorkItemPhase, note string) (ctrl.Result, error) {
	from := wi.Status.Phase
	wi.Status.Phase = next
	wi.Status.ActiveJob = nil
	if next.IsTerminal() {
		wi.Status.CompletedAt = ptrTime(metav1.Now())
	}
	if err := r.Status().Patch(ctx, wi, client.MergeFrom(orig)); err != nil {
		return ctrl.Result{}, err
	}
	r.Recorder.Eventf(wi, nil, corev1.EventTypeNormal, "PhaseChanged", "Reconcile", "%s → %s: %s", from, next, note)
	r.publishTransitionEvents(ctx, wi, from, next, note)
	return ctrl.Result{Requeue: !next.IsTerminal()}, nil
}

// publishTransitionEvents emits the phase change plus any milestone event the
// new status carries (analysis verdict, PR opened/ready, rollout decision).
func (r *WorkItemReconciler) publishTransitionEvents(ctx context.Context, wi *jarvisv1alpha1.WorkItem, from, next jarvisv1alpha1.WorkItemPhase, note string) {
	repo := repoLabel(wi)
	uid := string(wi.UID)
	r.publish(ctx, wi, jarvisevents.SubjectPhaseChanged,
		fmt.Sprintf("%s:phase:%s>%s", uid, from, next),
		jarvisevents.WorkflowPhaseChanged{
			Name: wi.Name, Repository: repo,
			FromPhase: string(from), ToPhase: string(next), Message: note,
		})

	if from == jarvisv1alpha1.PhaseAnalyzing && wi.Status.Analysis != nil {
		a := wi.Status.Analysis
		r.publish(ctx, wi, jarvisevents.SubjectAnalysisCompleted, uid+":analysis",
			jarvisevents.WorkflowAnalysisCompleted{
				Name: wi.Name, Repository: repo,
				Verdict: a.Verdict, Summary: a.Summary, Confidence: a.Confidence,
			})
	}
	if from == jarvisv1alpha1.PhaseDeveloping && next == jarvisv1alpha1.PhaseAwaitingCI && wi.Status.Development != nil {
		d := wi.Status.Development
		r.publish(ctx, wi, jarvisevents.SubjectPROpened,
			fmt.Sprintf("%s:propened:%d:%s", uid, d.PRNumber, d.HeadSHA),
			jarvisevents.WorkflowPROpened{
				Name: wi.Name, Repository: repo,
				PRURL: d.PRURL, PRNumber: d.PRNumber, Branch: d.Branch,
			})
	}
	if next == jarvisv1alpha1.PhaseAwaitingMerge && wi.Status.Development != nil {
		d := wi.Status.Development
		r.publish(ctx, wi, jarvisevents.SubjectPRReady,
			fmt.Sprintf("%s:prready:%d", uid, d.PRNumber),
			jarvisevents.WorkflowPRReady{
				Name: wi.Name, Repository: repo, PRURL: d.PRURL, PRNumber: d.PRNumber,
			})
	}
	if next == jarvisv1alpha1.PhaseSucceeded && wi.Status.Rollout != nil {
		ro := wi.Status.Rollout
		r.publish(ctx, wi, jarvisevents.SubjectRolloutCompleted, uid+":rollout",
			jarvisevents.WorkflowRolloutCompleted{
				Name: wi.Name, Repository: repo,
				Decision: ro.Decision, GitOpsCommitSHA: ro.GitOpsCommitSHA,
				GitOpsPRURL: ro.GitOpsPRURL, ArgoCDApp: ro.ArgoCDApp,
			})
	}
}

// fail moves the WorkItem to Failed.
func (r *WorkItemReconciler) fail(ctx context.Context, orig, wi *jarvisv1alpha1.WorkItem, reason, message string) (ctrl.Result, error) {
	wi.Status.Phase = jarvisv1alpha1.PhaseFailed
	wi.Status.FailureReason = fmt.Sprintf("%s: %s", reason, message)
	wi.Status.CompletedAt = ptrTime(metav1.Now())
	wi.Status.ActiveJob = nil
	if err := r.Status().Patch(ctx, wi, client.MergeFrom(orig)); err != nil {
		return ctrl.Result{}, err
	}
	r.Recorder.Eventf(wi, nil, corev1.EventTypeWarning, "Failed", "Reconcile", "%s: %s", reason, message)
	r.publish(ctx, wi, jarvisevents.SubjectFailed, string(wi.UID)+":failed",
		jarvisevents.WorkflowFailed{
			Name: wi.Name, Repository: repoLabel(wi),
			Phase: string(orig.Status.Phase), Reason: wi.Status.FailureReason,
		})
	return ctrl.Result{}, nil
}

// terminationMessage finds the agent container's termination message from the
// Job's pod(s), preferring the most recent pod.
func (r *WorkItemReconciler) terminationMessage(ctx context.Context, job *batchv1.Job) (string, error) {
	var pods corev1.PodList
	if err := r.List(ctx, &pods, client.InNamespace(job.Namespace),
		client.MatchingLabels{"job-name": job.Name}); err != nil {
		return "", err
	}
	sort.Slice(pods.Items, func(i, j int) bool {
		return pods.Items[j].CreationTimestamp.Before(&pods.Items[i].CreationTimestamp)
	})
	for _, pod := range pods.Items {
		for _, cs := range pod.Status.ContainerStatuses {
			if cs.Name == "agent" && cs.State.Terminated != nil && cs.State.Terminated.Message != "" {
				return cs.State.Terminated.Message, nil
			}
		}
	}
	return "", nil
}

func jobFinished(job *batchv1.Job) (complete, failed bool) {
	for _, cond := range job.Status.Conditions {
		if cond.Status != corev1.ConditionTrue {
			continue
		}
		switch cond.Type {
		case batchv1.JobComplete:
			complete = true
		case batchv1.JobFailed:
			failed = true
		}
	}
	return complete, failed
}

func findJobCondition(job *batchv1.Job, t batchv1.JobConditionType) *batchv1.JobCondition {
	for i := range job.Status.Conditions {
		if job.Status.Conditions[i].Type == t && job.Status.Conditions[i].Status == corev1.ConditionTrue {
			return &job.Status.Conditions[i]
		}
	}
	return nil
}

func setCond(wi *jarvisv1alpha1.WorkItem, condType string, status metav1.ConditionStatus, reason, message string) {
	meta.SetStatusCondition(&wi.Status.Conditions, metav1.Condition{
		Type:               condType,
		Status:             status,
		Reason:             nonEmptyReason(reason),
		Message:            message,
		ObservedGeneration: wi.Generation,
	})
}

// nonEmptyReason keeps metav1.Condition validation happy.
func nonEmptyReason(reason string) string {
	if reason == "" {
		return "Unknown"
	}
	return reason
}

func ptrTime(t metav1.Time) *metav1.Time { return &t }

// publish sends a workflow event to NATS; failures are surfaced as K8s
// events but never block the pipeline (JetStream dedupe makes replays safe).
func (r *WorkItemReconciler) publish(ctx context.Context, wi *jarvisv1alpha1.WorkItem, subject, msgID string, data any) {
	if r.Events == nil {
		return
	}
	if err := r.Events.Publish(ctx, subject, msgID, data); err != nil {
		logf.FromContext(ctx).Error(err, "event publish failed", "subject", subject)
		r.Recorder.Eventf(wi, nil, corev1.EventTypeWarning, "EventPublishFailed", "Reconcile", "%s: %v", subject, err)
	}
}

func repoLabel(wi *jarvisv1alpha1.WorkItem) string {
	if name := wi.Labels[jarvisv1alpha1.LabelRepository]; name != "" {
		return name
	}
	return wi.Spec.RepositoryRef.Name
}

// SetupWithManager sets up the controller with the Manager.
func (r *WorkItemReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&jarvisv1alpha1.WorkItem{}).
		Owns(&batchv1.Job{}).
		Named("workitem").
		Complete(r)
}
