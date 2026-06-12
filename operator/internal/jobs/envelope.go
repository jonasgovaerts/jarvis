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
	"encoding/json"
	"fmt"
)

// Envelope is the Go mirror of jarvis_core.envelope.AgentResultEnvelope —
// the contract agents write to /dev/termination-log. Keep in sync with
// libs/jarvis-core/src/jarvis_core/envelope.py.
type Envelope struct {
	Version   int               `json:"version"`
	Outcome   string            `json:"outcome"` // success | failure
	Stage     string            `json:"stage"`
	Result    json.RawMessage   `json:"result,omitempty"`
	Artifacts map[string]string `json:"artifacts,omitempty"`
	Error     *EnvelopeError    `json:"error,omitempty"`
}

// EnvelopeError carries a failure's machine-readable cause and whether the
// operator should retry the stage.
type EnvelopeError struct {
	Reason    string `json:"reason"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

// Succeeded reports whether the agent finished its stage successfully.
func (e *Envelope) Succeeded() bool { return e.Outcome == "success" }

// DecodeResult unmarshals the stage result into the given typed struct.
func (e *Envelope) DecodeResult(into any) error {
	if e.Result == nil {
		return fmt.Errorf("envelope has no result")
	}
	return json.Unmarshal(e.Result, into)
}

// ParseEnvelope parses a pod termination message into an Envelope. A message
// that is not a valid envelope (e.g. FallbackToLogsOnError tail output after
// a crash) yields an error — the caller treats that as a retryable failure.
func ParseEnvelope(raw string) (*Envelope, error) {
	var env Envelope
	if err := json.Unmarshal([]byte(raw), &env); err != nil {
		return nil, fmt.Errorf("termination message is not an agent envelope: %w", err)
	}
	if env.Outcome != "success" && env.Outcome != "failure" {
		return nil, fmt.Errorf("envelope has invalid outcome %q", env.Outcome)
	}
	return &env, nil
}
