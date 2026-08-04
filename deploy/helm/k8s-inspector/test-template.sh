#!/usr/bin/env sh
set -eu

CHART_DIR="${CHART_DIR:-deploy/helm/k8s-inspector}"
RELEASE_NAME="${RELEASE_NAME:-k8s-inspector}"

render_and_check() {
  name="$1"
  values_file="$2"
  expected_path="$3"
  expected_probe="$4"
  output_file="$(mktemp)"

  helm template "${RELEASE_NAME}" "${CHART_DIR}" \
    -f "${CHART_DIR}/ci-values.yaml" \
    -f "${CHART_DIR}/${values_file}" >"${output_file}"

  grep -q "path: ${expected_path}" "${output_file}"
  grep -q "path: ${expected_probe}" "${output_file}"

  rm -f "${output_file}"
  printf '%s\n' "ok ${name}"
}

render_and_check "root" "values-root.yaml" "/" "/health/ready"
render_and_check "subpath" "values-subpath.yaml" "/inspector" "/inspector/health/ready"

dual_output="$(mktemp)"
helm template "${RELEASE_NAME}" "${CHART_DIR}" \
  -f "${CHART_DIR}/ci-values.yaml" \
  -f "${CHART_DIR}/values-dual.yaml" >"${dual_output}"

grep -q "name: ${RELEASE_NAME}-k8s-inspector-dual-entry" "${dual_output}"
grep -q "path: /$" "${dual_output}"
grep -q "path: /inspector" "${dual_output}"
grep -q "path: /health/ready" "${dual_output}"

rm -f "${dual_output}"
printf '%s\n' "ok dual"
