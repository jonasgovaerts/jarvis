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

// Package forge holds the minimal GitHub client the operator needs:
// polling PR merge state during AwaitingMerge. Everything heavier lives in
// the Python agents.
package forge

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// BaseURL is variable for tests.
var BaseURL = "https://api.github.com"

var httpClient = &http.Client{Timeout: 15 * time.Second}

// PRMergeState reports whether a PR is merged and its merge commit SHA.
func PRMergeState(ctx context.Context, token, owner, repo string, number int) (bool, string, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/pulls/%d", BaseURL, owner, repo, number)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, "", err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")

	resp, err := httpClient.Do(req)
	if err != nil {
		return false, "", err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		return false, "", fmt.Errorf("github pulls/%d: HTTP %d", number, resp.StatusCode)
	}

	var pr struct {
		Merged         bool   `json:"merged"`
		MergeCommitSHA string `json:"merge_commit_sha"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&pr); err != nil {
		return false, "", err
	}
	return pr.Merged, pr.MergeCommitSHA, nil
}

// MergePR squash-merges a pull request and returns the merge commit SHA.
func MergePR(ctx context.Context, token, owner, repo string, number int) (string, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/pulls/%d/merge", BaseURL, owner, repo, number)
	body := strings.NewReader(`{"merge_method":"squash"}`)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, url, body)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("github merge pulls/%d: HTTP %d", number, resp.StatusCode)
	}
	var result struct {
		SHA string `json:"sha"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}
	return result.SHA, nil
}
