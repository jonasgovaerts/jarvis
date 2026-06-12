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

package jobs

import (
	"fmt"
	"os"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"

	jarvisv1alpha1 "github.com/jonasgovaerts/jarvis/operator/api/v1alpha1"
)

// Per-stage default Job deadlines (seconds).
var defaultTimeouts = map[jarvisv1alpha1.AgentStage]int64{
	jarvisv1alpha1.StageAnalyzer:  600,
	jarvisv1alpha1.StageDeveloper: 3600,
	jarvisv1alpha1.StageDevOps:    3600,
	jarvisv1alpha1.StageSRE:       2400, // includes waiting for the merge commit's image build
}

const (
	DefaultMaxRetries   = 2
	agentServiceAccount = "jarvis-agent"
)

// DefaultAgentImage resolves the agent image from the manager environment so
// deploys can pin it without recompiling.
func DefaultAgentImage() string {
	if img := os.Getenv("JARVIS_AGENT_IMAGE"); img != "" {
		return img
	}
	return "ghcr.io/jonasgovaerts/jarvis/agents:latest"
}

// DefaultModel is the platform fallback when neither the WorkItem nor the
// ManagedRepository pins a model for a stage.
func DefaultModel() string {
	if m := os.Getenv("JARVIS_DEFAULT_MODEL"); m != "" {
		return m
	}
	return "claude-sonnet"
}

// JobName returns the deterministic per-attempt Job name.
func JobName(wi *jarvisv1alpha1.WorkItem, stage jarvisv1alpha1.AgentStage, attempt int32) string {
	name := fmt.Sprintf("%s-%s-r%d", wi.Name, stage, attempt)
	if len(name) > 63 {
		name = name[len(name)-63:]
	}
	return name
}

// ResolveModel applies the override chain: WorkItem > ManagedRepository > platform default.
func ResolveModel(wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository, stage jarvisv1alpha1.AgentStage) jarvisv1alpha1.ModelSpec {
	if m, ok := wi.Spec.ModelOverrides[stage]; ok {
		return m
	}
	if a, ok := repo.Spec.Pipeline.Agents[stage]; ok && a.Model != nil {
		return *a.Model
	}
	return jarvisv1alpha1.ModelSpec{Model: DefaultModel()}
}

// Build assembles the agent Job for one stage attempt. The operator owns
// retries (backoffLimit=0); results come back via the termination message.
func Build(wi *jarvisv1alpha1.WorkItem, repo *jarvisv1alpha1.ManagedRepository, stage jarvisv1alpha1.AgentStage, attempt int32) *batchv1.Job {
	agentCfg := repo.Spec.Pipeline.Agents[stage]

	image := DefaultAgentImage()
	if agentCfg.Image != "" {
		image = agentCfg.Image
	}
	timeout := defaultTimeouts[stage]
	if agentCfg.TimeoutSeconds != nil {
		timeout = *agentCfg.TimeoutSeconds
	}
	model := ResolveModel(wi, repo, stage)

	env := []corev1.EnvVar{
		{Name: "JARVIS_WORKITEM_NAME", Value: wi.Name},
		{Name: "JARVIS_WORKITEM_NAMESPACE", Value: wi.Namespace},
		{Name: "JARVIS_STAGE", Value: string(stage)},
		{Name: "JARVIS_MODEL", Value: model.Model},
		{Name: "LLM_BASE_URL", Value: os.Getenv("JARVIS_LLM_BASE_URL")},
	}
	if model.MaxTokens != nil {
		env = append(env, corev1.EnvVar{Name: "JARVIS_MAX_TOKENS", Value: fmt.Sprint(*model.MaxTokens)})
	}
	if model.Temperature != "" {
		env = append(env, corev1.EnvVar{Name: "JARVIS_TEMPERATURE", Value: model.Temperature})
	}

	volumes := []corev1.Volume{{
		Name: "repo-token",
		VolumeSource: corev1.VolumeSource{
			Secret: &corev1.SecretVolumeSource{SecretName: repo.Spec.CredentialsSecretRef.Name},
		},
	}, {
		Name: "llm-key",
		VolumeSource: corev1.VolumeSource{
			Secret: &corev1.SecretVolumeSource{
				SecretName: "llm-agent-key",
				Optional:   ptr.To(true),
			},
		},
	}}
	mounts := []corev1.VolumeMount{
		{Name: "repo-token", MountPath: "/var/run/secrets/jarvis/repo", ReadOnly: true},
		{Name: "llm-key", MountPath: "/var/run/secrets/jarvis/llm", ReadOnly: true},
	}
	if stage == jarvisv1alpha1.StageSRE && repo.Spec.GitOps != nil {
		volumes = append(volumes, corev1.Volume{
			Name: "gitops-token",
			VolumeSource: corev1.VolumeSource{
				Secret: &corev1.SecretVolumeSource{SecretName: repo.Spec.GitOps.CredentialsSecretRef.Name},
			},
		})
		mounts = append(mounts, corev1.VolumeMount{
			Name: "gitops-token", MountPath: "/var/run/secrets/jarvis/gitops", ReadOnly: true,
		})
	}

	return &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      JobName(wi, stage, attempt),
			Namespace: wi.Namespace,
			Labels: map[string]string{
				jarvisv1alpha1.LabelWorkItem: wi.Name,
				jarvisv1alpha1.LabelStage:    string(stage),
			},
		},
		Spec: batchv1.JobSpec{
			BackoffLimit:            ptr.To(int32(0)),
			ActiveDeadlineSeconds:   ptr.To(timeout),
			TTLSecondsAfterFinished: ptr.To(int32(86400)),
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						jarvisv1alpha1.LabelWorkItem: wi.Name,
						jarvisv1alpha1.LabelStage:    string(stage),
					},
				},
				Spec: corev1.PodSpec{
					ServiceAccountName: agentServiceAccount,
					RestartPolicy:      corev1.RestartPolicyNever,
					Containers: []corev1.Container{{
						Name:                     "agent",
						Image:                    image,
						Command:                  []string{"jarvis-agent", string(stage)},
						Env:                      env,
						VolumeMounts:             mounts,
						TerminationMessagePolicy: corev1.TerminationMessageFallbackToLogsOnError,
					}},
					Volumes: volumes,
				},
			},
		},
	}
}
