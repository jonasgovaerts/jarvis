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
	"time"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"

	jarvisv1alpha1 "github.com/jonasgovaerts/jarvis/operator/api/v1alpha1"
)

const repoResyncInterval = 10 * time.Minute

// ManagedRepositoryReconciler validates repository configuration (referenced
// secrets exist) and maintains the active WorkItem count.
type ManagedRepositoryReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=jarvis.dev,resources=managedrepositories,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=jarvis.dev,resources=managedrepositories/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=jarvis.dev,resources=managedrepositories/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch

func (r *ManagedRepositoryReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	repo := &jarvisv1alpha1.ManagedRepository{}
	if err := r.Get(ctx, req.NamespacedName, repo); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}
	orig := repo.DeepCopy()

	r.checkSecret(ctx, repo, repo.Spec.CredentialsSecretRef.Name, jarvisv1alpha1.CondCredentialsValid)
	if repo.Spec.GitOps != nil {
		r.checkSecret(ctx, repo, repo.Spec.GitOps.CredentialsSecretRef.Name, jarvisv1alpha1.CondGitOpsReachable)
	} else {
		meta.RemoveStatusCondition(&repo.Status.Conditions, jarvisv1alpha1.CondGitOpsReachable)
	}

	var items jarvisv1alpha1.WorkItemList
	if err := r.List(ctx, &items, client.InNamespace(repo.Namespace),
		client.MatchingLabels{jarvisv1alpha1.LabelRepository: repo.Name}); err != nil {
		return ctrl.Result{}, err
	}
	active := int32(0)
	for _, item := range items.Items {
		if item.Status.Phase != "" && !item.Status.Phase.IsTerminal() {
			active++
		}
	}
	repo.Status.ActiveWorkItems = active

	if err := r.Status().Patch(ctx, repo, client.MergeFrom(orig)); err != nil {
		return ctrl.Result{}, err
	}
	return ctrl.Result{RequeueAfter: repoResyncInterval}, nil
}

// checkSecret sets the given condition based on the secret's existence and
// the presence of a "token" key. Live provider validation (a real API call)
// arrives with the forge client.
func (r *ManagedRepositoryReconciler) checkSecret(ctx context.Context, repo *jarvisv1alpha1.ManagedRepository, name, condType string) {
	secret := &corev1.Secret{}
	err := r.Get(ctx, client.ObjectKey{Namespace: repo.Namespace, Name: name}, secret)

	cond := metav1.Condition{
		Type:               condType,
		Status:             metav1.ConditionTrue,
		Reason:             "SecretPresent",
		ObservedGeneration: repo.Generation,
	}
	switch {
	case apierrors.IsNotFound(err):
		cond.Status = metav1.ConditionFalse
		cond.Reason = "SecretMissing"
		cond.Message = fmt.Sprintf("secret %q not found", name)
	case err != nil:
		cond.Status = metav1.ConditionUnknown
		cond.Reason = "SecretCheckError"
		cond.Message = err.Error()
	case len(secret.Data["token"]) == 0:
		cond.Status = metav1.ConditionFalse
		cond.Reason = "TokenKeyMissing"
		cond.Message = fmt.Sprintf("secret %q has no %q key", name, "token")
	}
	meta.SetStatusCondition(&repo.Status.Conditions, cond)
}

// SetupWithManager sets up the controller with the Manager.
func (r *ManagedRepositoryReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&jarvisv1alpha1.ManagedRepository{}).
		Watches(&jarvisv1alpha1.WorkItem{}, handler.EnqueueRequestsFromMapFunc(r.mapWorkItemToRepo)).
		Named("managedrepository").
		Complete(r)
}

// mapWorkItemToRepo re-reconciles the repository whenever one of its
// WorkItems changes, keeping activeWorkItems fresh.
func (r *ManagedRepositoryReconciler) mapWorkItemToRepo(_ context.Context, obj client.Object) []ctrl.Request {
	wi, ok := obj.(*jarvisv1alpha1.WorkItem)
	if !ok || wi.Spec.RepositoryRef.Name == "" {
		return nil
	}
	return []ctrl.Request{{
		NamespacedName: client.ObjectKey{Namespace: wi.Namespace, Name: wi.Spec.RepositoryRef.Name},
	}}
}
