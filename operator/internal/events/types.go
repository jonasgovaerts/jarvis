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

package events

// Payload structs mirror the camelCase wire schemas in schemas/*.json
// (generated from jarvis_core.events). Hand-maintained; the contracts-drift
// CI lane guards the Python side, review guards this one.

type WorkflowCreated struct {
	Name       string `json:"name"`
	Namespace  string `json:"namespace"`
	Repository string `json:"repository"`
	SourceType string `json:"sourceType"`
	Title      string `json:"title"`
}

type WorkflowPhaseChanged struct {
	Name       string `json:"name"`
	Repository string `json:"repository"`
	FromPhase  string `json:"fromPhase"`
	ToPhase    string `json:"toPhase"`
	Message    string `json:"message"`
}

type WorkflowAnalysisCompleted struct {
	Name       string `json:"name"`
	Repository string `json:"repository"`
	Verdict    string `json:"verdict"`
	Summary    string `json:"summary"`
	Confidence string `json:"confidence"`
}

type WorkflowPROpened struct {
	Name       string `json:"name"`
	Repository string `json:"repository"`
	PRURL      string `json:"prUrl"`
	PRNumber   int    `json:"prNumber"`
	Branch     string `json:"branch"`
}

type WorkflowPRReady struct {
	Name       string `json:"name"`
	Repository string `json:"repository"`
	PRURL      string `json:"prUrl"`
	PRNumber   int    `json:"prNumber"`
}

type WorkflowRolloutCompleted struct {
	Name            string `json:"name"`
	Repository      string `json:"repository"`
	Decision        string `json:"decision"`
	GitOpsCommitSHA string `json:"gitopsCommitSha"`
	GitOpsPRURL     string `json:"gitopsPrUrl"`
	ArgoCDApp       string `json:"argocdApp"`
}

type WorkflowFailed struct {
	Name       string `json:"name"`
	Repository string `json:"repository"`
	Phase      string `json:"phase"`
	Reason     string `json:"reason"`
}
