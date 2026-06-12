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

// Package events publishes Jarvis workflow events to NATS JetStream.
//
// Wire contract: CloudEvents-lite envelopes on subjects jarvis.workflow.*,
// mirroring libs/jarvis-core/src/jarvis_core/events.py (schemas/ is the
// language-neutral source). Deterministic Nats-Msg-Id headers + the stream's
// duplicate window give effectively-once delivery.
package events

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

const (
	StreamName = "JARVIS_EVENTS"
	source     = "operator"
)

// Subjects published by the operator (single-writer rule: only the operator
// publishes jarvis.workflow.*).
const (
	SubjectCreated           = "jarvis.workflow.created"
	SubjectPhaseChanged      = "jarvis.workflow.phase.changed"
	SubjectAnalysisCompleted = "jarvis.workflow.analysis.completed"
	SubjectPROpened          = "jarvis.workflow.pr.opened"
	SubjectPRReady           = "jarvis.workflow.pr.ready"
	SubjectRolloutCompleted  = "jarvis.workflow.rollout.completed"
	SubjectFailed            = "jarvis.workflow.failed"
)

// Envelope mirrors jarvis_core.events.EventEnvelope.
type Envelope struct {
	ID     string `json:"id"`
	Type   string `json:"type"`
	Source string `json:"source"`
	Time   string `json:"time"`
	Data   any    `json:"data"`
}

// Publisher is the seam the controller depends on; nil-safe usage is the
// caller's job (envtest runs without NATS).
type Publisher interface {
	Publish(ctx context.Context, subject, msgID string, data any) error
}

// NATSPublisher publishes to a JetStream stream, creating it if needed.
type NATSPublisher struct {
	js jetstream.JetStream
}

// NewNATSPublisher connects and ensures the JARVIS_EVENTS stream exists.
func NewNATSPublisher(ctx context.Context, url string) (*NATSPublisher, error) {
	conn, err := nats.Connect(url,
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		return nil, fmt.Errorf("nats connect: %w", err)
	}
	js, err := jetstream.New(conn)
	if err != nil {
		return nil, fmt.Errorf("jetstream init: %w", err)
	}
	_, err = js.CreateOrUpdateStream(ctx, jetstream.StreamConfig{
		Name:       StreamName,
		Subjects:   []string{"jarvis.>"},
		Storage:    jetstream.FileStorage,
		MaxAge:     30 * 24 * time.Hour,
		Duplicates: 10 * time.Minute,
	})
	if err != nil {
		return nil, fmt.Errorf("ensure stream: %w", err)
	}
	return &NATSPublisher{js: js}, nil
}

// Publish wraps data in the envelope and publishes with a dedupe message ID.
func (p *NATSPublisher) Publish(ctx context.Context, subject, msgID string, data any) error {
	payload, err := json.Marshal(Envelope{
		ID:     uuid.NewString(),
		Type:   subject,
		Source: source,
		Time:   time.Now().UTC().Format(time.RFC3339),
		Data:   data,
	})
	if err != nil {
		return err
	}
	msg := &nats.Msg{Subject: subject, Data: payload}
	msg.Header = nats.Header{}
	msg.Header.Set("Nats-Msg-Id", msgID)
	_, err = p.js.PublishMsg(ctx, msg)
	return err
}
