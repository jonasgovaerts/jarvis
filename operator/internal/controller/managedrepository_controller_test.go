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
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"

	jarvisv1alpha1 "github.com/jonasgovaerts/jarvis/operator/api/v1alpha1"
)

var _ = Describe("ManagedRepository controller", func() {
	ns := "default"

	reconcile := func(name string) *jarvisv1alpha1.ManagedRepository {
		r := &ManagedRepositoryReconciler{Client: k8sClient, Scheme: k8sClient.Scheme()}
		_, err := r.Reconcile(ctx, ctrl.Request{
			NamespacedName: types.NamespacedName{Name: name, Namespace: ns},
		})
		ExpectWithOffset(1, err).NotTo(HaveOccurred())
		repo := &jarvisv1alpha1.ManagedRepository{}
		ExpectWithOffset(1, k8sClient.Get(ctx,
			types.NamespacedName{Name: name, Namespace: ns}, repo)).To(Succeed())
		return repo
	}

	It("flags missing credentials secrets and recovers when they appear", func() {
		repo := &jarvisv1alpha1.ManagedRepository{
			ObjectMeta: metav1.ObjectMeta{Name: "mr-creds", Namespace: ns},
			Spec: jarvisv1alpha1.ManagedRepositorySpec{
				Provider: "github", Owner: "acme", Name: "api",
				CredentialsSecretRef: corev1.LocalObjectReference{Name: "mr-creds-token"},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		repo = reconcile("mr-creds")
		cond := meta.FindStatusCondition(repo.Status.Conditions, jarvisv1alpha1.CondCredentialsValid)
		Expect(cond).NotTo(BeNil())
		Expect(cond.Status).To(Equal(metav1.ConditionFalse))
		Expect(cond.Reason).To(Equal("SecretMissing"))

		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{Name: "mr-creds-token", Namespace: ns},
			Data:       map[string][]byte{"token": []byte("ghp_test")},
		}
		Expect(k8sClient.Create(ctx, secret)).To(Succeed())

		repo = reconcile("mr-creds")
		cond = meta.FindStatusCondition(repo.Status.Conditions, jarvisv1alpha1.CondCredentialsValid)
		Expect(cond.Status).To(Equal(metav1.ConditionTrue))
	})

	It("rejects secrets without a token key", func() {
		secret := &corev1.Secret{
			ObjectMeta: metav1.ObjectMeta{Name: "mr-badkey-token", Namespace: ns},
			Data:       map[string][]byte{"password": []byte("nope")},
		}
		Expect(k8sClient.Create(ctx, secret)).To(Succeed())

		repo := &jarvisv1alpha1.ManagedRepository{
			ObjectMeta: metav1.ObjectMeta{Name: "mr-badkey", Namespace: ns},
			Spec: jarvisv1alpha1.ManagedRepositorySpec{
				Provider: "github", Owner: "acme", Name: "api",
				CredentialsSecretRef: corev1.LocalObjectReference{Name: "mr-badkey-token"},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		repo = reconcile("mr-badkey")
		cond := meta.FindStatusCondition(repo.Status.Conditions, jarvisv1alpha1.CondCredentialsValid)
		Expect(cond.Status).To(Equal(metav1.ConditionFalse))
		Expect(cond.Reason).To(Equal("TokenKeyMissing"))
	})
})
