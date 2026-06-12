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

package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// WorkItemPhase is the pipeline state machine position. Terminal phases are
// Succeeded, Failed and Skipped.
// +kubebuilder:validation:Enum=Pending;Analyzing;Developing;AwaitingCI;AwaitingMerge;RolloutCheck;Succeeded;Failed;Skipped
type WorkItemPhase string

const (
	PhasePending       WorkItemPhase = "Pending"
	PhaseAnalyzing     WorkItemPhase = "Analyzing"
	PhaseDeveloping    WorkItemPhase = "Developing"
	PhaseAwaitingCI    WorkItemPhase = "AwaitingCI"
	PhaseAwaitingMerge WorkItemPhase = "AwaitingMerge"
	PhaseRolloutCheck  WorkItemPhase = "RolloutCheck"
	PhaseSucceeded     WorkItemPhase = "Succeeded"
	PhaseFailed        WorkItemPhase = "Failed"
	PhaseSkipped       WorkItemPhase = "Skipped"
)

// IsTerminal reports whether the phase ends the pipeline.
func (p WorkItemPhase) IsTerminal() bool {
	return p == PhaseSucceeded || p == PhaseFailed || p == PhaseSkipped
}

// AgentStage identifies one of the four agent kinds the operator spawns.
// +kubebuilder:validation:Enum=analyzer;developer;devops;sre
type AgentStage string

const (
	StageAnalyzer  AgentStage = "analyzer"
	StageDeveloper AgentStage = "developer"
	StageDevOps    AgentStage = "devops"
	StageSRE       AgentStage = "sre"
)

// SourceType discriminates where a WorkItem came from.
// +kubebuilder:validation:Enum=Issue;FeatureRequest
type SourceType string

const (
	SourceIssue          SourceType = "Issue"
	SourceFeatureRequest SourceType = "FeatureRequest"
)

// IssueSource references a provider issue. The provider-global ID is the
// dedupe key the issue-watcher uses for idempotent WorkItem creation.
type IssueSource struct {
	// +kubebuilder:validation:Enum=github;gitlab
	Provider string `json:"provider"`
	// Provider-global ID (GitHub node_id).
	ID     string `json:"id"`
	Number int    `json:"number"`
	URL    string `json:"url"`
	Title  string `json:"title"`
	// +optional
	Labels []string `json:"labels,omitempty"`
}

// FeatureRequestSource captures a chat-initiated request.
type FeatureRequestSource struct {
	Description string `json:"description"`
	RequestedBy string `json:"requestedBy"`
	// +optional
	ConversationID string `json:"conversationId,omitempty"`
}

// WorkItemSource is a tagged union over the two entry points.
type WorkItemSource struct {
	Type SourceType `json:"type"`
	// +optional
	Issue *IssueSource `json:"issue,omitempty"`
	// +optional
	FeatureRequest *FeatureRequestSource `json:"featureRequest,omitempty"`
}

// Title returns the human-readable headline for either source kind.
func (s *WorkItemSource) TitleText() string {
	switch s.Type {
	case SourceIssue:
		if s.Issue != nil {
			return s.Issue.Title
		}
	case SourceFeatureRequest:
		if s.FeatureRequest != nil {
			return s.FeatureRequest.Description
		}
	}
	return ""
}

// ModelSpec selects an LLM via the LiteLLM proxy's logical model names.
type ModelSpec struct {
	// LiteLLM logical model name, e.g. "claude-sonnet".
	Model string `json:"model"`
	// +optional
	MaxTokens *int32 `json:"maxTokens,omitempty"`
	// Stringified float to keep CRDs integer/string-only, e.g. "0.2".
	// +optional
	Temperature string `json:"temperature,omitempty"`
}

// WorkItemSpec defines the desired state of WorkItem. Immutable after
// creation except suspend.
type WorkItemSpec struct {
	// Name of the ManagedRepository in the same namespace this work targets.
	RepositoryRef corev1.LocalObjectReference `json:"repositoryRef"`

	Source WorkItemSource `json:"source"`

	// Per-stage model overrides; fall back to the ManagedRepository pipeline
	// config, then platform defaults.
	// +optional
	ModelOverrides map[AgentStage]ModelSpec `json:"modelOverrides,omitempty"`

	// Suspend pauses the pipeline: a running Job finishes, no new phase starts.
	// +optional
	Suspend bool `json:"suspend,omitempty"`

	// Delete this WorkItem N seconds after reaching a terminal phase.
	// +optional
	TTLSecondsAfterFinished *int64 `json:"ttlSecondsAfterFinished,omitempty"`
}

// AnalysisResult is the analyzer stage outcome.
type AnalysisResult struct {
	// +kubebuilder:validation:Enum=CodeChange;Misconfiguration;NotActionable
	Verdict string `json:"verdict"`
	Summary string `json:"summary"`
	// +optional
	Confidence string `json:"confidence,omitempty"`
	// Name of the ConfigMap holding the full analysis report.
	// +optional
	ReportRef string `json:"reportRef,omitempty"`
}

// DevelopmentResult is the developer stage outcome.
type DevelopmentResult struct {
	Branch   string `json:"branch"`
	PRURL    string `json:"prUrl"`
	PRNumber int    `json:"prNumber"`
	HeadSHA  string `json:"headSha"`
}

// CIResult is the devops stage outcome.
type CIResult struct {
	// +kubebuilder:validation:Enum=Pending;Running;Passed;Failed;TimedOut
	Status string `json:"status"`
	// +optional
	CheckSuiteURL string `json:"checkSuiteUrl,omitempty"`
	// LLM root-cause summary, set when Status=Failed; fed back into the
	// developer stage on fix loops.
	// +optional
	FailureAnalysis string `json:"failureAnalysis,omitempty"`
	// +optional
	Merged bool `json:"merged,omitempty"`
	// +optional
	MergeSHA string `json:"mergeSha,omitempty"`
}

// RolloutResult is the sre stage outcome.
type RolloutResult struct {
	// +kubebuilder:validation:Enum=Required;NotRequired
	Decision string `json:"decision"`
	// +optional
	Reason string `json:"reason,omitempty"`
	// +optional
	GitOpsCommitSHA string `json:"gitopsCommitSha,omitempty"`
	// +optional
	GitOpsPRURL string `json:"gitopsPrUrl,omitempty"`
	// +optional
	ArgoCDApp string `json:"argocdApp,omitempty"`
}

// Condition types set on WorkItem.
const (
	CondAnalyzed        = "Analyzed"
	CondPRCreated       = "PRCreated"
	CondCIPassed        = "CIPassed"
	CondMerged          = "Merged"
	CondRolloutDecided  = "RolloutDecided"
	CondEventsPublished = "EventsPublished"
)

// WorkItemStatus defines the observed state of WorkItem. Only the operator
// writes it; agents report via Job termination messages.
type WorkItemStatus struct {
	// +optional
	Phase WorkItemPhase `json:"phase,omitempty"`

	// +listType=map
	// +listMapKey=type
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// +optional
	Analysis *AnalysisResult `json:"analysis,omitempty"`
	// +optional
	Development *DevelopmentResult `json:"development,omitempty"`
	// +optional
	CI *CIResult `json:"ci,omitempty"`
	// +optional
	Rollout *RolloutResult `json:"rollout,omitempty"`

	// Attempt count per phase, operator-managed.
	// +optional
	Retries map[string]int32 `json:"retries,omitempty"`
	// AwaitingCI -> Developing fix loops consumed.
	// +optional
	CIFixAttempts int32 `json:"ciFixAttempts,omitempty"`

	// Reference to the currently running agent Job, if any.
	// +optional
	ActiveJob *corev1.ObjectReference `json:"activeJob,omitempty"`
	// +optional
	StartedAt *metav1.Time `json:"startedAt,omitempty"`
	// +optional
	CompletedAt *metav1.Time `json:"completedAt,omitempty"`
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
	// +optional
	FailureReason string `json:"failureReason,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Repo",type=string,JSONPath=`.spec.repositoryRef.name`
// +kubebuilder:printcolumn:name="Source",type=string,JSONPath=`.spec.source.type`
// +kubebuilder:printcolumn:name="PR",type=string,JSONPath=`.status.development.prUrl`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// WorkItem is one unit of work flowing through the agent pipeline — a
// provider issue or a chat feature request.
type WorkItem struct {
	metav1.TypeMeta `json:",inline"`

	// +optional
	metav1.ObjectMeta `json:"metadata,omitzero"`

	// +required
	Spec WorkItemSpec `json:"spec"`

	// +optional
	Status WorkItemStatus `json:"status,omitzero"`
}

// +kubebuilder:object:root=true

// WorkItemList contains a list of WorkItem
type WorkItemList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitzero"`
	Items           []WorkItem `json:"items"`
}

// Well-known labels and annotations.
const (
	LabelRepository    = "jarvis.dev/repository"
	LabelSourceType    = "jarvis.dev/source-type"
	LabelWorkItem      = "jarvis.dev/workitem"
	LabelStage         = "jarvis.dev/stage"
	AnnotationAction   = "jarvis.dev/requested-action" // approve | retry | cancel
	AnnotationExtClose = "jarvis.dev/external-close"
	WorkItemFinalizer  = "jarvis.dev/finalizer"
)

func init() {
	SchemeBuilder.Register(&WorkItem{}, &WorkItemList{})
}
