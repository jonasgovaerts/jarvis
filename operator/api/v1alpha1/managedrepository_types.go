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

// IssueSelector controls which provider issues become WorkItems. An empty
// RequireLabels means every open issue is picked up — the recommended setup
// is an explicit opt-in label like "jarvis".
type IssueSelector struct {
	// +optional
	RequireLabels []string `json:"requireLabels,omitempty"`
	// +optional
	ExcludeLabels []string `json:"excludeLabels,omitempty"`
}

// GitOpsSpec maps a repository to its GitOps deployment location. Repos
// without it skip the RolloutCheck phase.
type GitOpsSpec struct {
	RepoURL string `json:"repoUrl"`
	// Directory inside the gitops repo, e.g. "apps/myservice".
	Path string `json:"path"`
	// +kubebuilder:default=main
	// +optional
	TargetBranch string `json:"targetBranch,omitempty"`
	// +optional
	ArgoCDApp string `json:"argocdApp,omitempty"`
	// +kubebuilder:validation:Enum=DirectPush;PullRequest
	// +kubebuilder:default=PullRequest
	// +optional
	UpdateStrategy string `json:"updateStrategy,omitempty"`
	// Secret (same namespace, key "token") with push rights on the gitops repo.
	CredentialsSecretRef corev1.LocalObjectReference `json:"credentialsSecretRef"`
	// Hint for the SRE agent on how image tags appear in the manifests.
	// +kubebuilder:validation:Enum=KustomizeImage;HelmValues
	// +kubebuilder:default=KustomizeImage
	// +optional
	ManifestStyle string `json:"manifestStyle,omitempty"`
}

// AgentSpec tunes one pipeline stage for this repository.
type AgentSpec struct {
	// +optional
	Model *ModelSpec `json:"model,omitempty"`
	// Override the default agent image.
	// +optional
	Image string `json:"image,omitempty"`
	// Job activeDeadlineSeconds for this stage.
	// +optional
	TimeoutSeconds *int64 `json:"timeoutSeconds,omitempty"`
	// +optional
	MaxRetries *int32 `json:"maxRetries,omitempty"`
}

// PipelineSpec configures pipeline behavior per repository.
type PipelineSpec struct {
	// +kubebuilder:default=2
	// +optional
	MaxConcurrentWorkItems int32 `json:"maxConcurrentWorkItems,omitempty"`
	// AutoMerge lets the devops agent squash-merge green PRs; default is a
	// human merge after the pr.ready notification.
	// +optional
	AutoMerge bool `json:"autoMerge,omitempty"`
	// Keys: analyzer, developer, devops, sre.
	// +optional
	Agents map[AgentStage]AgentSpec `json:"agents,omitempty"`
}

// ManagedRepositorySpec defines the desired state of ManagedRepository
type ManagedRepositorySpec struct {
	// +kubebuilder:validation:Enum=github;gitlab
	Provider string `json:"provider"`
	Owner    string `json:"owner"`
	Name     string `json:"name"`

	// Secret (same namespace, key "token") used to read issues, clone, push
	// branches, open PRs and read checks.
	CredentialsSecretRef corev1.LocalObjectReference `json:"credentialsSecretRef"`

	// +optional
	IssueSelector *IssueSelector `json:"issueSelector,omitempty"`

	// +optional
	GitOps *GitOpsSpec `json:"gitops,omitempty"`

	// +optional
	Pipeline PipelineSpec `json:"pipeline,omitempty"`

	// Suspend stops new WorkItem creation and pauses phase transitions.
	// +optional
	Suspend bool `json:"suspend,omitempty"`
}

// Condition types set on ManagedRepository.
const (
	CondCredentialsValid = "CredentialsValid"
	CondGitOpsReachable  = "GitOpsReachable"
)

// ManagedRepositoryStatus defines the observed state of ManagedRepository.
type ManagedRepositoryStatus struct {
	// +listType=map
	// +listMapKey=type
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Patched by the issue-watcher after each successful poll.
	// +optional
	LastIssueSync *metav1.Time `json:"lastIssueSync,omitempty"`

	// Count of non-terminal WorkItems referencing this repository.
	// +optional
	ActiveWorkItems int32 `json:"activeWorkItems,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Provider",type=string,JSONPath=`.spec.provider`
// +kubebuilder:printcolumn:name="Owner",type=string,JSONPath=`.spec.owner`
// +kubebuilder:printcolumn:name="Name",type=string,JSONPath=`.spec.name`
// +kubebuilder:printcolumn:name="Active",type=integer,JSONPath=`.status.activeWorkItems`
// +kubebuilder:printcolumn:name="Suspended",type=boolean,JSONPath=`.spec.suspend`

// ManagedRepository configures one repository Jarvis watches and works on.
type ManagedRepository struct {
	metav1.TypeMeta `json:",inline"`

	// +optional
	metav1.ObjectMeta `json:"metadata,omitzero"`

	// +required
	Spec ManagedRepositorySpec `json:"spec"`

	// +optional
	Status ManagedRepositoryStatus `json:"status,omitzero"`
}

// FullName returns "owner/name".
func (r *ManagedRepository) FullName() string {
	return r.Spec.Owner + "/" + r.Spec.Name
}

// +kubebuilder:object:root=true

// ManagedRepositoryList contains a list of ManagedRepository
type ManagedRepositoryList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitzero"`
	Items           []ManagedRepository `json:"items"`
}

func init() {
	SchemeBuilder.Register(&ManagedRepository{}, &ManagedRepositoryList{})
}
