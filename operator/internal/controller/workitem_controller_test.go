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
	"encoding/json"
	"fmt"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/events"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"

	jarvisv1alpha1 "github.com/jonasgovaerts/jarvis/operator/api/v1alpha1"
	"github.com/jonasgovaerts/jarvis/operator/internal/jobs"
)

var _ = Describe("WorkItem controller", func() {
	var (
		r       *WorkItemReconciler
		ns      = "default"
		counter int
	)

	BeforeEach(func() {
		r = &WorkItemReconciler{
			Client:   k8sClient,
			Scheme:   k8sClient.Scheme(),
			Recorder: events.NewFakeRecorder(100),
		}
		counter++
	})

	newRepo := func(name string, mutate func(*jarvisv1alpha1.ManagedRepository)) *jarvisv1alpha1.ManagedRepository {
		repo := &jarvisv1alpha1.ManagedRepository{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: ns},
			Spec: jarvisv1alpha1.ManagedRepositorySpec{
				Provider:             "github",
				Owner:                "acme",
				Name:                 "api",
				CredentialsSecretRef: corev1.LocalObjectReference{Name: "repo-token"},
			},
		}
		if mutate != nil {
			mutate(repo)
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())
		return repo
	}

	newWorkItem := func(name, repoName string) *jarvisv1alpha1.WorkItem {
		wi := &jarvisv1alpha1.WorkItem{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: ns},
			Spec: jarvisv1alpha1.WorkItemSpec{
				RepositoryRef: corev1.LocalObjectReference{Name: repoName},
				Source: jarvisv1alpha1.WorkItemSource{
					Type: jarvisv1alpha1.SourceIssue,
					Issue: &jarvisv1alpha1.IssueSource{
						Provider: "github", ID: "I_abc", Number: 42,
						URL: "https://github.com/acme/api/issues/42", Title: "fix login",
					},
				},
			},
		}
		Expect(k8sClient.Create(ctx, wi)).To(Succeed())
		return wi
	}

	reconcile := func(wi *jarvisv1alpha1.WorkItem) ctrl.Result {
		res, err := r.Reconcile(ctx, ctrl.Request{
			NamespacedName: types.NamespacedName{Name: wi.Name, Namespace: wi.Namespace},
		})
		ExpectWithOffset(1, err).NotTo(HaveOccurred())
		ExpectWithOffset(1, k8sClient.Get(ctx,
			types.NamespacedName{Name: wi.Name, Namespace: wi.Namespace}, wi)).To(Succeed())
		return res
	}

	// reconcileUntil drives reconciliation until the WorkItem reaches the phase.
	reconcileUntil := func(wi *jarvisv1alpha1.WorkItem, phase jarvisv1alpha1.WorkItemPhase) {
		for range 10 {
			if wi.Status.Phase == phase {
				return
			}
			reconcile(wi)
		}
		ExpectWithOffset(1, wi.Status.Phase).To(Equal(phase))
	}

	// completeJob marks the stage Job finished and plants the envelope as the
	// agent pod's termination message.
	completeJob := func(wi *jarvisv1alpha1.WorkItem, stage jarvisv1alpha1.AgentStage, envelope map[string]any) {
		attempt := wi.Status.Retries[string(wi.Status.Phase)]
		jobName := jobs.JobName(wi, stage, attempt)

		job := &batchv1.Job{}
		ExpectWithOffset(1, k8sClient.Get(ctx,
			types.NamespacedName{Name: jobName, Namespace: ns}, job)).To(Succeed())

		raw, err := json.Marshal(envelope)
		ExpectWithOffset(1, err).NotTo(HaveOccurred())

		pod := &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      jobName + "-pod",
				Namespace: ns,
				Labels:    map[string]string{"job-name": jobName},
			},
			Spec: corev1.PodSpec{
				RestartPolicy: corev1.RestartPolicyNever,
				Containers:    []corev1.Container{{Name: "agent", Image: "stub"}},
			},
		}
		ExpectWithOffset(1, k8sClient.Create(ctx, pod)).To(Succeed())
		pod.Status = corev1.PodStatus{
			Phase: corev1.PodSucceeded,
			ContainerStatuses: []corev1.ContainerStatus{{
				Name: "agent",
				State: corev1.ContainerState{Terminated: &corev1.ContainerStateTerminated{
					ExitCode: 0, Message: string(raw),
				}},
			}},
		}
		ExpectWithOffset(1, k8sClient.Status().Update(ctx, pod)).To(Succeed())

		now := metav1.Now()
		job.Status.StartTime = &now
		job.Status.CompletionTime = &now
		job.Status.Conditions = append(job.Status.Conditions,
			batchv1.JobCondition{Type: batchv1.JobSuccessCriteriaMet, Status: corev1.ConditionTrue},
			batchv1.JobCondition{Type: batchv1.JobComplete, Status: corev1.ConditionTrue},
		)
		ExpectWithOffset(1, k8sClient.Status().Update(ctx, job)).To(Succeed())
	}

	successEnvelope := func(stage jarvisv1alpha1.AgentStage, result map[string]any) map[string]any {
		return map[string]any{
			"version": 1, "outcome": "success", "stage": string(stage), "result": result,
		}
	}

	failureEnvelope := func(stage jarvisv1alpha1.AgentStage, retryable bool) map[string]any {
		return map[string]any{
			"version": 1, "outcome": "failure", "stage": string(stage),
			"error": map[string]any{"reason": "Boom", "message": "it broke", "retryable": retryable},
		}
	}

	It("walks the happy path to Succeeded (no gitops mapping)", func() {
		repo := newRepo(fmt.Sprintf("repo-happy-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-happy-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		Expect(wi.Labels[jarvisv1alpha1.LabelRepository]).To(Equal(repo.Name))

		reconcile(wi) // spawns analyzer job
		Expect(wi.Status.ActiveJob).NotTo(BeNil())
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, successEnvelope(jarvisv1alpha1.StageAnalyzer,
			map[string]any{"verdict": "CodeChange", "summary": "null deref", "confidence": "high"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseDeveloping)
		Expect(wi.Status.Analysis.Verdict).To(Equal("CodeChange"))

		reconcile(wi) // spawns developer job
		completeJob(wi, jarvisv1alpha1.StageDeveloper, successEnvelope(jarvisv1alpha1.StageDeveloper,
			map[string]any{"branch": "jarvis/issue-42", "prUrl": "https://github.com/acme/api/pull/7",
				"prNumber": 7, "headSha": "abc1234"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseAwaitingCI)
		Expect(wi.Status.Development.PRNumber).To(Equal(7))

		reconcile(wi) // spawns devops job
		completeJob(wi, jarvisv1alpha1.StageDevOps, successEnvelope(jarvisv1alpha1.StageDevOps,
			map[string]any{"status": "Passed", "merged": true, "mergeSha": "def5678"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseRolloutCheck)

		reconcileUntil(wi, jarvisv1alpha1.PhaseSucceeded)
		Expect(wi.Status.Rollout.Decision).To(Equal("NotRequired"))
		Expect(wi.Status.CompletedAt).NotTo(BeNil())
	})

	It("skips NotActionable issues", func() {
		repo := newRepo(fmt.Sprintf("repo-skip-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-skip-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, successEnvelope(jarvisv1alpha1.StageAnalyzer,
			map[string]any{"verdict": "NotActionable", "summary": "duplicate"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseSkipped)
	})

	It("routes misconfigurations straight to RolloutCheck", func() {
		repo := newRepo(fmt.Sprintf("repo-misconf-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-misconf-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, successEnvelope(jarvisv1alpha1.StageAnalyzer,
			map[string]any{"verdict": "Misconfiguration", "summary": "bad env var"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseSucceeded) // no gitops mapping → done
	})

	It("retries retryable failures and fails when exhausted", func() {
		one := int32(1)
		repo := newRepo(fmt.Sprintf("repo-retry-%d", counter), func(r *jarvisv1alpha1.ManagedRepository) {
			r.Spec.Pipeline.Agents = map[jarvisv1alpha1.AgentStage]jarvisv1alpha1.AgentSpec{
				jarvisv1alpha1.StageAnalyzer: {MaxRetries: &one},
			}
		})
		wi := newWorkItem(fmt.Sprintf("wi-retry-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		reconcile(wi) // attempt 0 job
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, failureEnvelope(jarvisv1alpha1.StageAnalyzer, true))
		reconcile(wi)
		Expect(wi.Status.Retries["Analyzing"]).To(Equal(int32(1)))
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseAnalyzing))

		reconcile(wi) // attempt 1 job
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, failureEnvelope(jarvisv1alpha1.StageAnalyzer, true))
		reconcile(wi)
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseFailed))
		Expect(wi.Status.FailureReason).To(ContainSubstring("Boom"))
	})

	It("fails immediately on non-retryable failures", func() {
		repo := newRepo(fmt.Sprintf("repo-fatal-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-fatal-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, failureEnvelope(jarvisv1alpha1.StageAnalyzer, false))
		reconcile(wi)
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseFailed))
	})

	It("loops back to Developing when CI fails, then gives up", func() {
		repo := newRepo(fmt.Sprintf("repo-fixloop-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-fixloop-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, successEnvelope(jarvisv1alpha1.StageAnalyzer,
			map[string]any{"verdict": "CodeChange", "summary": "bug"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseDeveloping)

		for fix := 1; fix <= 2; fix++ {
			reconcile(wi) // developer job for this round
			completeJob(wi, jarvisv1alpha1.StageDeveloper, successEnvelope(jarvisv1alpha1.StageDeveloper,
				map[string]any{"branch": "b", "prUrl": "u", "prNumber": 1, "headSha": fmt.Sprintf("sha%d", fix)}))
			reconcileUntil(wi, jarvisv1alpha1.PhaseAwaitingCI)

			reconcile(wi) // devops job
			completeJob(wi, jarvisv1alpha1.StageDevOps, successEnvelope(jarvisv1alpha1.StageDevOps,
				map[string]any{"status": "Failed", "failureAnalysis": "tests red"}))
			reconcile(wi)
			if fix < 2 {
				Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseDeveloping))
				Expect(wi.Status.CIFixAttempts).To(Equal(int32(fix)))
			}
		}
		// After the second CI failure the fix budget is spent: third failure → Failed.
		reconcile(wi) // developer job round 3
		completeJob(wi, jarvisv1alpha1.StageDeveloper, successEnvelope(jarvisv1alpha1.StageDeveloper,
			map[string]any{"branch": "b", "prUrl": "u", "prNumber": 1, "headSha": "sha3"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseAwaitingCI)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageDevOps, successEnvelope(jarvisv1alpha1.StageDevOps,
			map[string]any{"status": "Failed", "failureAnalysis": "still red"}))
		reconcile(wi)
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseFailed))
	})

	It("parks green unmerged PRs in AwaitingMerge until merged", func() {
		repo := newRepo(fmt.Sprintf("repo-merge-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-merge-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageAnalyzer, successEnvelope(jarvisv1alpha1.StageAnalyzer,
			map[string]any{"verdict": "CodeChange", "summary": "bug"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseDeveloping)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageDeveloper, successEnvelope(jarvisv1alpha1.StageDeveloper,
			map[string]any{"branch": "b", "prUrl": "u", "prNumber": 1, "headSha": "abc"}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseAwaitingCI)
		reconcile(wi)
		completeJob(wi, jarvisv1alpha1.StageDevOps, successEnvelope(jarvisv1alpha1.StageDevOps,
			map[string]any{"status": "Passed", "merged": false}))
		reconcileUntil(wi, jarvisv1alpha1.PhaseAwaitingMerge)

		// Still waiting.
		res := reconcile(wi)
		Expect(res.RequeueAfter).To(Equal(awaitingMergeRequeue))
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseAwaitingMerge))

		// Simulate the merge being observed (step 7 forge poll stand-in).
		orig := wi.DeepCopy()
		wi.Status.CI.Merged = true
		wi.Status.CI.MergeSHA = "merged123"
		Expect(k8sClient.Status().Patch(ctx, wi, client.MergeFrom(orig))).To(Succeed())
		reconcileUntil(wi, jarvisv1alpha1.PhaseSucceeded)
	})

	It("respects spec.suspend before spawning new jobs", func() {
		repo := newRepo(fmt.Sprintf("repo-susp-%d", counter), nil)
		wi := newWorkItem(fmt.Sprintf("wi-susp-%d", counter), repo.Name)

		reconcileUntil(wi, jarvisv1alpha1.PhaseAnalyzing)

		Expect(k8sClient.Get(ctx, types.NamespacedName{Name: wi.Name, Namespace: ns}, wi)).To(Succeed())
		wi.Spec.Suspend = true
		Expect(k8sClient.Update(ctx, wi)).To(Succeed())

		res := reconcile(wi)
		Expect(res.RequeueAfter).To(Equal(suspendedRequeue))
		jobName := jobs.JobName(wi, jarvisv1alpha1.StageAnalyzer, 0)
		err := k8sClient.Get(ctx, types.NamespacedName{Name: jobName, Namespace: ns}, &batchv1.Job{})
		Expect(err).To(HaveOccurred(), "no job should be spawned while suspended")
	})
})
