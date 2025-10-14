#!/bin/bash

# Comprehensive Test Execution Framework
# Enterprise RAG System - Production Validation
# Copyright: Sean McDonnell - Proprietary and Confidential

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEST_RESULTS_DIR="${PROJECT_ROOT}/test-results"
BASELINE_FILE="${PROJECT_ROOT}/baseline-measurements.json"
SLA_FILE="${PROJECT_ROOT}/sla-requirements.yaml"

# Test execution parameters
TEST_CATEGORIES="${1:-all}"
EXECUTION_MODE="${2:-sequential}"
STOP_ON_FAILURE="${3:-false}"
GENERATE_REPORT="${4:-true}"

# Logging setup
LOG_FILE="${TEST_RESULTS_DIR}/test-execution-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "${TEST_RESULTS_DIR}"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" | tee -a "${LOG_FILE}"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" | tee -a "${LOG_FILE}" >&2
}

warn() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] $1" | tee -a "${LOG_FILE}"
}

# Test result tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
declare -a FAILED_TEST_NAMES

record_test_result() {
    local test_name="$1"
    local result="$2"
    local duration="$3"
    local details="$4"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [[ "$result" == "PASS" ]]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        log "TEST PASSED: $test_name (${duration}s)"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_TEST_NAMES+=("$test_name: $details")
        error "TEST FAILED: $test_name (${duration}s) - $details"
        
        if [[ "$STOP_ON_FAILURE" == "true" ]]; then
            error "Stopping test execution due to failure"
            exit 1
        fi
    fi
}

# Test execution functions
execute_test() {
    local test_script="$1"
    local test_name="$2"
    local timeout="${3:-3600}"  # Default 1 hour timeout
    
    log "Starting test: $test_name"
    local start_time=$(date +%s)
    
    # Execute test with timeout
    if timeout "$timeout" "$test_script" > "${TEST_RESULTS_DIR}/${test_name}.log" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        record_test_result "$test_name" "PASS" "$duration" "Test completed successfully"
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        local exit_code=$?
        local error_details="Exit code: $exit_code, Check ${TEST_RESULTS_DIR}/${test_name}.log"
        record_test_result "$test_name" "FAIL" "$duration" "$error_details"
    fi
}

# Pre-test validation
validate_environment() {
    log "Validating test environment..."
    
    # Check Kubernetes connectivity
    if ! kubectl cluster-info > /dev/null 2>&1; then
        error "Kubernetes cluster not accessible"
        exit 1
    fi
    
    # Check required namespaces
    if ! kubectl get namespace enterprise-rag > /dev/null 2>&1; then
        error "Enterprise RAG namespace not found"
        exit 1
    fi
    
    # Verify external services
    local services=("anthropic" "voyage" "cohere" "pinecone")
    for service in "${services[@]}"; do
        if ! "${SCRIPT_DIR}/../validation/check-external-service.sh" "$service"; then
            warn "External service $service may not be available"
        fi
    done
    
    log "Environment validation completed"
}

# Test category execution
execute_functional_tests() {
    log "=== EXECUTING FUNCTIONAL TESTS ==="
    
    # Unit tests
    execute_test "${SCRIPT_DIR}/../testing/unit-tests.sh" "unit-tests" 1800
    
    # Integration tests
    execute_test "${SCRIPT_DIR}/../testing/integration-tests.sh" "integration-tests" 3600
    
    # API contract tests
    execute_test "${SCRIPT_DIR}/../testing/api-contract-tests.sh" "api-contract-tests" 1800
    
    # End-to-end workflow tests
    execute_test "${SCRIPT_DIR}/../testing/e2e-workflow-tests.sh" "e2e-workflow-tests" 3600
}

execute_performance_tests() {
    log "=== EXECUTING PERFORMANCE TESTS ==="
    
    # Baseline performance measurement
    execute_test "${SCRIPT_DIR}/../performance/baseline-measurement.sh" "baseline-measurement" 1800
    
    # Load testing at normal capacity
    execute_test "${SCRIPT_DIR}/../performance/load-test-normal.sh" "load-test-normal" 7200
    
    # Stress testing at 10x capacity
    execute_test "${SCRIPT_DIR}/../performance/stress-test-extreme.sh" "stress-test-extreme" 7200
    
    # Response time validation
    execute_test "${SCRIPT_DIR}/../performance/response-time-validation.sh" "response-time-validation" 3600
    
    # Throughput validation
    execute_test "${SCRIPT_DIR}/../performance/throughput-validation.sh" "throughput-validation" 86400
    
    # Resource utilization validation
    execute_test "${SCRIPT_DIR}/../performance/resource-validation.sh" "resource-validation" 3600
}

execute_reliability_tests() {
    log "=== EXECUTING RELIABILITY TESTS ==="
    
    # Database failure testing
    execute_test "${SCRIPT_DIR}/../failure/database-failure-test.sh" "database-failure-test" 1800
    
    # Node failure testing
    execute_test "${SCRIPT_DIR}/../failure/node-failure-test.sh" "node-failure-test" 3600
    
    # Network partition testing
    execute_test "${SCRIPT_DIR}/../failure/network-partition-test.sh" "network-partition-test" 1800
    
    # External service failure testing
    execute_test "${SCRIPT_DIR}/../failure/external-service-failure-test.sh" "external-service-failure-test" 3600
    
    # Resource exhaustion testing
    execute_test "${SCRIPT_DIR}/../failure/resource-exhaustion-test.sh" "resource-exhaustion-test" 7200
}

execute_security_tests() {
    log "=== EXECUTING SECURITY TESTS ==="
    
    # Authentication stress testing
    execute_test "${SCRIPT_DIR}/../security/auth-stress-test.sh" "auth-stress-test" 3600
    
    # Authorization boundary testing
    execute_test "${SCRIPT_DIR}/../security/authz-boundary-test.sh" "authz-boundary-test" 1800
    
    # Input validation testing
    execute_test "${SCRIPT_DIR}/../security/input-validation-test.sh" "input-validation-test" 3600
    
    # Penetration testing
    execute_test "${SCRIPT_DIR}/../security/penetration-test.sh" "penetration-test" 7200
}

execute_chaos_tests() {
    log "=== EXECUTING CHAOS ENGINEERING TESTS ==="
    
    # Random failure injection
    execute_test "${SCRIPT_DIR}/../chaos/random-failure-injection.sh" "random-failure-injection" 86400
    
    # Byzantine failure testing
    execute_test "${SCRIPT_DIR}/../chaos/byzantine-failure-test.sh" "byzantine-failure-test" 7200
    
    # Partial failure handling
    execute_test "${SCRIPT_DIR}/../chaos/partial-failure-test.sh" "partial-failure-test" 3600
}

execute_endurance_tests() {
    log "=== EXECUTING ENDURANCE TESTS ==="
    
    # 72-hour endurance test
    execute_test "${SCRIPT_DIR}/../endurance/72hour-endurance-test.sh" "72hour-endurance-test" 259200
    
    # Memory leak detection
    execute_test "${SCRIPT_DIR}/../endurance/memory-leak-detection.sh" "memory-leak-detection" 86400
    
    # Performance stability validation
    execute_test "${SCRIPT_DIR}/../endurance/performance-stability-test.sh" "performance-stability-test" 86400
}

# Report generation
generate_test_report() {
    local report_file="${TEST_RESULTS_DIR}/comprehensive-test-report-$(date +%Y%m%d-%H%M%S).html"
    
    log "Generating comprehensive test report: $report_file"
    
    cat > "$report_file" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Enterprise RAG System - Test Execution Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { background-color: #f5f5f5; padding: 20px; border-radius: 5px; }
        .summary { margin: 20px 0; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .test-details { margin: 20px 0; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .failure-details { background-color: #fff2f2; padding: 10px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Enterprise RAG System - Test Execution Report</h1>
        <p><strong>Execution Date:</strong> $(date)</p>
        <p><strong>Test Categories:</strong> $TEST_CATEGORIES</p>
        <p><strong>Execution Mode:</strong> $EXECUTION_MODE</p>
    </div>
    
    <div class="summary">
        <h2>Test Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Tests Executed</td><td>$TOTAL_TESTS</td></tr>
            <tr><td>Passed Tests</td><td class="pass">$PASSED_TESTS</td></tr>
            <tr><td>Failed Tests</td><td class="fail">$FAILED_TESTS</td></tr>
            <tr><td>Success Rate</td><td>$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%</td></tr>
        </table>
    </div>
EOF

    if [[ $FAILED_TESTS -gt 0 ]]; then
        cat >> "$report_file" << EOF
    <div class="failure-details">
        <h3>Failed Tests</h3>
        <ul>
EOF
        for failed_test in "${FAILED_TEST_NAMES[@]}"; do
            echo "            <li>$failed_test</li>" >> "$report_file"
        done
        cat >> "$report_file" << EOF
        </ul>
    </div>
EOF
    fi
    
    cat >> "$report_file" << EOF
    <div class="test-details">
        <h2>Detailed Test Results</h2>
        <p>Individual test logs are available in: <code>$TEST_RESULTS_DIR</code></p>
    </div>
</body>
</html>
EOF

    log "Test report generated: $report_file"
}

# Main execution flow
main() {
    log "Starting comprehensive test execution"
    log "Test categories: $TEST_CATEGORIES"
    log "Execution mode: $EXECUTION_MODE"
    log "Stop on failure: $STOP_ON_FAILURE"
    
    # Environment validation
    validate_environment
    
    # Test execution based on categories
    case "$TEST_CATEGORIES" in
        "all")
            execute_functional_tests
            execute_performance_tests
            execute_reliability_tests
            execute_security_tests
            execute_chaos_tests
            execute_endurance_tests
            ;;
        "functional")
            execute_functional_tests
            ;;
        "performance")
            execute_performance_tests
            ;;
        "reliability")
            execute_reliability_tests
            ;;
        "security")
            execute_security_tests
            ;;
        "chaos")
            execute_chaos_tests
            ;;
        "endurance")
            execute_endurance_tests
            ;;
        *)
            error "Unknown test category: $TEST_CATEGORIES"
            exit 1
            ;;
    esac
    
    # Generate report
    if [[ "$GENERATE_REPORT" == "true" ]]; then
        generate_test_report
    fi
    
    # Final summary
    log "=== TEST EXECUTION SUMMARY ==="
    log "Total tests: $TOTAL_TESTS"
    log "Passed: $PASSED_TESTS"
    log "Failed: $FAILED_TESTS"
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        log "ALL TESTS PASSED - System ready for production"
        exit 0
    else
        error "TESTS FAILED - System NOT ready for production"
        exit 1
    fi
}

# Trap for cleanup
cleanup() {
    log "Cleaning up test execution..."
    # Kill any background processes
    jobs -p | xargs -r kill
}
trap cleanup EXIT

# Execute main function
main "$@"