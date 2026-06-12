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
	"net/http"
	"net/http/httptest"

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
	"github.com/jonasgovaerts/jarvis/operator/internal/forge"
)

var _ = Describe("Dashboard card actions", func() {
	var r *WorkItemReconciler
	ns := "default"

	BeforeEach(func() {
		r = &WorkItemReconciler{
			Client:   k8sClient,
			Scheme:   k8sClient.Scheme(),
			Recorder: events.NewFakeRecorder(100),
		}
	})

	annotate := func(wi *jarvisv1alpha1.WorkItem, action string) {
		Expect(k8sClient.Get(ctx, types.NamespacedName{Name: wi.Name, Namespace: ns}, wi)).To(Succeed())
		patched := wi.DeepCopy()
		if patched.Annotations == nil {
			patched.Annotations = map[string]string{}
		}
		patched.Annotations[jarvisv1alpha1.AnnotationAction] = action
		Expect(k8sClient.Patch(ctx, patched, client.MergeFrom(wi))).To(Succeed())
	}

	reconcile := func(wi *jarvisv1alpha1.WorkItem) {
		_, err := r.Reconcile(ctx, ctrl.Request{
			NamespacedName: types.NamespacedName{Name: wi.Name, Namespace: ns},
		})
		ExpectWithOffset(1, err).NotTo(HaveOccurred())
		ExpectWithOffset(1, k8sClient.Get(ctx,
			types.NamespacedName{Name: wi.Name, Namespace: ns}, wi)).To(Succeed())
	}

	makeRepoAndItem := func(suffix string) (*jarvisv1alpha1.ManagedRepository, *jarvisv1alpha1.WorkItem) {
		repo := &jarvisv1alpha1.ManagedRepository{
			ObjectMeta: metav1.ObjectMeta{Name: "act-repo-" + suffix, Namespace: ns},
			Spec: jarvisv1alpha1.ManagedRepositorySpec{
				Provider: "github", Owner: "acme", Name: "api",
				CredentialsSecretRef: corev1.LocalObjectReference{Name: "act-token-" + suffix},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())
		wi := &jarvisv1alpha1.WorkItem{
			ObjectMeta: metav1.ObjectMeta{Name: "act-wi-" + suffix, Namespace: ns},
			Spec: jarvisv1alpha1.WorkItemSpec{
				RepositoryRef: corev1.LocalObjectReference{Name: repo.Name},
				Source: jarvisv1alpha1.WorkItemSource{
					Type: jarvisv1alpha1.SourceIssue,
					Issue: &jarvisv1alpha1.IssueSource{
						Provider: "github", ID: "I_a", Number: 1, URL: "u", Title: "t",
					},
				},
			},
		}
		Expect(k8sClient.Create(ctx, wi)).To(Succeed())
		return repo, wi
	}

	setPhase := func(wi *jarvisv1alpha1.WorkItem, mutate func(*jarvisv1alpha1.WorkItemStatus)) {
		Expect(k8sClient.Get(ctx, types.NamespacedName{Name: wi.Name, Namespace: ns}, wi)).To(Succeed())
		orig := wi.DeepCopy()
		mutate(&wi.Status)
		Expect(k8sClient.Status().Patch(ctx, wi, client.MergeFrom(orig))).To(Succeed())
	}

	It("cancel sends a running item to Skipped", func() {
		_, wi := makeRepoAndItem("cancel")
		reconcile(wi) // -> Pending (also adds finalizer)
		setPhase(wi, func(s *jarvisv1alpha1.WorkItemStatus) {
			s.Phase = jarvisv1alpha1.PhaseDeveloping
		})
		annotate(wi, "cancel")
		reconcile(wi)
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseSkipped))
		Expect(wi.Annotations).NotTo(HaveKey(jarvisv1alpha1.AnnotationAction))
	})

	It("retry restarts a Failed item from scratch and removes stale jobs", func() {
		_, wi := makeRepoAndItem("retry")
		reconcile(wi)
		staleJob := &batchv1.Job{
			ObjectMeta: metav1.ObjectMeta{
				Name:      wi.Name + "-analyzer-r0",
				Namespace: ns,
				Labels:    map[string]string{jarvisv1alpha1.LabelWorkItem: wi.Name},
			},
			Spec: batchv1.JobSpec{
				Template: corev1.PodTemplateSpec{
					Spec: corev1.PodSpec{
						RestartPolicy: corev1.RestartPolicyNever,
						Containers:    []corev1.Container{{Name: "agent", Image: "stub"}},
					},
				},
			},
		}
		Expect(k8sClient.Create(ctx, staleJob)).To(Succeed())
		setPhase(wi, func(s *jarvisv1alpha1.WorkItemStatus) {
			s.Phase = jarvisv1alpha1.PhaseFailed
			s.FailureReason = "Boom"
			s.CompletedAt = ptrTime(metav1.Now())
			s.Retries = map[string]int32{"Analyzing": 2}
		})
		annotate(wi, "retry")
		reconcile(wi)
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhasePending))
		Expect(wi.Status.FailureReason).To(BeEmpty())
		Expect(wi.Status.Retries).To(BeEmpty())

		// The stale job must be gone (or terminating) so attempt 0 reruns fresh.
		Eventually(func() bool {
			job := &batchv1.Job{}
			err := k8sClient.Get(ctx, types.NamespacedName{Name: staleJob.Name, Namespace: ns}, job)
			return err != nil || !job.DeletionTimestamp.IsZero()
		}, "5s", "250ms").Should(BeTrue())
	})

	It("approve merges the PR and moves to RolloutCheck", func() {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			Expect(req.Method).To(Equal(http.MethodPut))
			Expect(req.URL.Path).To(Equal("/repos/acme/api/pulls/7/merge"))
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"sha":"merged-sha-123","merged":true}`))
		}))
		defer server.Close()
		oldBase := forge.BaseURL
		forge.BaseURL = server.URL
		defer func() { forge.BaseURL = oldBase }()

		_, wi := makeRepoAndItem("approve")
		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{Name: "act-token-approve", Namespace: ns},
			Data:       map[string][]byte{"token": []byte("tok")},
		}
		Expect(k8sClient.Create(ctx, secret)).To(Succeed())

		reconcile(wi)
		setPhase(wi, func(s *jarvisv1alpha1.WorkItemStatus) {
			s.Phase = jarvisv1alpha1.PhaseAwaitingMerge
			s.Development = &jarvisv1alpha1.DevelopmentResult{
				Branch: "b", PRURL: "u", PRNumber: 7, HeadSHA: "h",
			}
			s.CI = &jarvisv1alpha1.CIResult{Status: "Passed"}
		})
		annotate(wi, "approve")
		reconcile(wi)
		Expect(wi.Status.Phase).To(Equal(jarvisv1alpha1.PhaseRolloutCheck))
		Expect(wi.Status.CI.Merged).To(BeTrue())
		Expect(wi.Status.CI.MergeSHA).To(Equal("merged-sha-123"))
	})
})
