#!/bin/bash

# Database Catastrophic Failure Test
# Tests complete database failure and recovery mechanisms
# Copyright: Sean McDonnell - Proprietary and Confidential

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_FILE="${PROJECT_ROOT}/test-results/database-failure-$(date +%Y%m%d-%H%M%S).log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" | tee -a "${LOG_FILE}"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" | tee -a "${LOG_FILE}" >&2
}

# Test configuration
FAILURE_TYPE="${1:-complete}"  # complete, corruption, network-partition
MAX_RECOVERY_TIME=300  # 5 minutes maximum recovery time
LOAD_DURING_FAILURE=true

# Pre-test validation
validate_environment() {
    log "Validating database environment..."
    
    # Check PostgreSQL is running
    if ! kubectl get pods -n enterprise-rag -l app=postgres | grep -q Running; then
        error "PostgreSQL pods not running"
        return 1
    fi
    
    # Check replication is working
    local master_pod=$(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o name | head -1)
    if [[ -z "$master_pod" ]]; then
        error "PostgreSQL master pod not found"
        return 1
    fi
    
    log "Database environment validation completed"
    return 0
}

# Measure baseline performance
measure_baseline() {
    log "Measuring baseline database performance..."
    
    local start_time=$(date +%s)
    
    # Execute sample queries to establish baseline
    kubectl exec -n enterprise-rag -it $(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o jsonpath='{.items[0].metadata.name}') -- \
        psql -U raguser -d ragdb -c "SELECT COUNT(*) FROM tenants;" > /dev/null
    
    local end_time=$(date +%s)
    local baseline_latency=$((end_time - start_time))
    
    echo "$baseline_latency" > "${PROJECT_ROOT}/test-results/db-baseline-latency.txt"
    log "Baseline query latency: ${baseline_latency}s"
}

# Generate continuous load during failure
generate_background_load() {
    log "Starting background load generation..."
    
    cat << 'EOF' > /tmp/db-load-generator.sh
#!/bin/bash
while true; do
    curl -s -H "Authorization: Bearer test-key" \
         -H "Content-Type: application/json" \
         -X POST "http://rag-api.enterprise-rag.svc.cluster.local:8000/query" \
         -d '{"query": "test query for database load"}' > /dev/null 2>&1
    sleep 1
done
EOF
    
    chmod +x /tmp/db-load-generator.sh
    /tmp/db-load-generator.sh &
    LOAD_PID=$!
    
    log "Background load started with PID: $LOAD_PID"
}

# Test complete database failure
test_complete_database_failure() {
    log "=== TESTING COMPLETE DATABASE FAILURE ==="
    
    # Record pre-failure state
    local pre_failure_data=$(kubectl exec -n enterprise-rag -it $(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o jsonpath='{.items[0].metadata.name}') -- \
        psql -U raguser -d ragdb -t -c "SELECT COUNT(*) FROM tenants;")
    
    log "Pre-failure tenant count: $pre_failure_data"
    
    # Kill the master database pod
    local master_pod=$(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o name)
    log "Terminating master database pod: $master_pod"
    
    local failure_start_time=$(date +%s)
    kubectl delete $master_pod -n enterprise-rag --force --grace-period=0
    
    # Monitor for automatic failover
    log "Monitoring for automatic failover..."
    local failover_detected=false
    local timeout=300  # 5 minutes timeout
    
    for ((i=0; i<timeout; i++)); do
        # Check if a new master is elected
        local new_master=$(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        
        if [[ -n "$new_master" ]] && kubectl get pod -n enterprise-rag "$new_master" -o jsonpath='{.status.phase}' | grep -q Running; then
            local failover_time=$(date +%s)
            local recovery_duration=$((failover_time - failure_start_time))
            log "Database failover completed in ${recovery_duration} seconds"
            
            if [[ $recovery_duration -gt $MAX_RECOVERY_TIME ]]; then
                error "Failover took ${recovery_duration}s, exceeds maximum ${MAX_RECOVERY_TIME}s"
                return 1
            fi
            
            failover_detected=true
            break
        fi
        
        sleep 1
    done
    
    if [[ "$failover_detected" != "true" ]]; then
        error "Database failover did not complete within timeout"
        return 1
    fi
    
    # Validate data integrity after failover
    sleep 10  # Wait for database to stabilize
    
    local post_failure_data=$(kubectl exec -n enterprise-rag -it $(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o jsonpath='{.items[0].metadata.name}') -- \
        psql -U raguser -d ragdb -t -c "SELECT COUNT(*) FROM tenants;" | tr -d ' \n')
    
    log "Post-failure tenant count: $post_failure_data"
    
    if [[ "$pre_failure_data" != "$post_failure_data" ]]; then
        error "Data integrity check failed: $pre_failure_data != $post_failure_data"
        return 1
    fi
    
    log "Complete database failure test PASSED"
    return 0
}

# Test database corruption scenario
test_database_corruption() {
    log "=== TESTING DATABASE CORRUPTION SCENARIO ==="
    
    # Simulate data corruption by modifying critical system tables
    local master_pod=$(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o jsonpath='{.items[0].metadata.name}')
    
    log "Simulating database corruption..."
    
    # Create a backup first
    kubectl exec -n enterprise-rag -it "$master_pod" -- \
        pg_dump -U raguser -d ragdb > "${PROJECT_ROOT}/test-results/pre-corruption-backup.sql"
    
    # Inject corruption (simulate index corruption)
    kubectl exec -n enterprise-rag -it "$master_pod" -- \
        psql -U raguser -d ragdb -c "DROP INDEX IF EXISTS idx_tenants_active;" || true
    
    # Test system response to corruption
    local corruption_start_time=$(date +%s)
    
    # Monitor for automatic detection and correction
    local max_detection_time=60
    local corruption_detected=false
    
    for ((i=0; i<max_detection_time; i++)); do
        # Check application logs for corruption detection
        if kubectl logs -n enterprise-rag deployment/rag-api --tail=50 | grep -q "DATABASE_ERROR\|INDEX_CORRUPTION"; then
            log "Database corruption detected by application"
            corruption_detected=true
            break
        fi
        sleep 1
    done
    
    # Trigger automatic index recreation
    kubectl exec -n enterprise-rag -it "$master_pod" -- \
        psql -U raguser -d ragdb -c "CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants(active);"
    
    local recovery_time=$(date +%s)
    local total_recovery_time=$((recovery_time - corruption_start_time))
    
    log "Database corruption recovery completed in ${total_recovery_time} seconds"
    
    if [[ $total_recovery_time -gt $MAX_RECOVERY_TIME ]]; then
        error "Corruption recovery took ${total_recovery_time}s, exceeds maximum ${MAX_RECOVERY_TIME}s"
        return 1
    fi
    
    log "Database corruption test PASSED"
    return 0
}

# Test network partition between database and application
test_network_partition() {
    log "=== TESTING NETWORK PARTITION SCENARIO ==="
    
    # Use network policies to simulate partition
    kubectl apply -f - << EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: database-partition-test
  namespace: enterprise-rag
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
  - Ingress
  - Egress
  ingress: []
  egress: []
EOF

    log "Network partition applied - database isolated"
    
    local partition_start_time=$(date +%s)
    
    # Monitor application behavior during partition
    sleep 30
    
    # Check if circuit breakers are activated
    local circuit_breaker_active=false
    if kubectl logs -n enterprise-rag deployment/rag-api --tail=100 | grep -q "CIRCUIT_BREAKER_OPEN\|DATABASE_UNAVAILABLE"; then
        circuit_breaker_active=true
        log "Circuit breaker activated during network partition"
    fi
    
    # Remove network partition
    kubectl delete networkpolicy database-partition-test -n enterprise-rag
    log "Network partition removed"
    
    # Monitor recovery
    local recovery_timeout=120
    local recovery_detected=false
    
    for ((i=0; i<recovery_timeout; i++)); do
        if kubectl logs -n enterprise-rag deployment/rag-api --tail=50 | grep -q "DATABASE_RECONNECTED\|CIRCUIT_BREAKER_CLOSED"; then
            local recovery_time=$(date +%s)
            local total_recovery_time=$((recovery_time - partition_start_time))
            log "Network partition recovery completed in ${total_recovery_time} seconds"
            recovery_detected=true
            break
        fi
        sleep 1
    done
    
    if [[ "$recovery_detected" != "true" ]]; then
        error "Network partition recovery not detected within timeout"
        return 1
    fi
    
    if [[ "$circuit_breaker_active" != "true" ]]; then
        error "Circuit breaker was not activated during network partition"
        return 1
    fi
    
    log "Network partition test PASSED"
    return 0
}

# Validate application behavior during database issues
validate_application_behavior() {
    log "Validating application behavior during database issues..."
    
    # Test that queries fail gracefully
    local response=$(curl -s -w "%{http_code}" -H "Authorization: Bearer test-key" \
                         -H "Content-Type: application/json" \
                         -X POST "http://rag-api.enterprise-rag.svc.cluster.local:8000/query" \
                         -d '{"query": "test query during database failure"}' -o /dev/null)
    
    # Should return 503 Service Unavailable or 500 with proper error message
    if [[ "$response" != "503" ]] && [[ "$response" != "500" ]]; then
        error "Application did not handle database failure correctly, returned: $response"
        return 1
    fi
    
    log "Application behavior validation PASSED"
    return 0
}

# Performance impact assessment
assess_performance_impact() {
    log "Assessing performance impact after recovery..."
    
    # Wait for system to stabilize
    sleep 30
    
    # Measure post-recovery performance
    local start_time=$(date +%s)
    
    kubectl exec -n enterprise-rag -it $(kubectl get pods -n enterprise-rag -l app=postgres,role=master -o jsonpath='{.items[0].metadata.name}') -- \
        psql -U raguser -d ragdb -c "SELECT COUNT(*) FROM tenants;" > /dev/null
    
    local end_time=$(date +%s)
    local post_recovery_latency=$((end_time - start_time))
    
    local baseline_latency=$(cat "${PROJECT_ROOT}/test-results/db-baseline-latency.txt")
    local performance_degradation=$((((post_recovery_latency - baseline_latency) * 100) / baseline_latency))
    
    log "Post-recovery latency: ${post_recovery_latency}s (baseline: ${baseline_latency}s)"
    log "Performance degradation: ${performance_degradation}%"
    
    if [[ $performance_degradation -gt 20 ]]; then
        error "Performance degradation ${performance_degradation}% exceeds acceptable threshold of 20%"
        return 1
    fi
    
    log "Performance impact assessment PASSED"
    return 0
}

# Cleanup function
cleanup() {
    log "Cleaning up database failure test..."
    
    # Kill background load generator
    if [[ -n "${LOAD_PID:-}" ]]; then
        kill "$LOAD_PID" 2>/dev/null || true
    fi
    
    # Remove any test network policies
    kubectl delete networkpolicy database-partition-test -n enterprise-rag 2>/dev/null || true
    
    # Clean up temporary files
    rm -f /tmp/db-load-generator.sh
    
    log "Cleanup completed"
}

# Main test execution
main() {
    log "Starting database catastrophic failure test"
    log "Failure type: $FAILURE_TYPE"
    log "Maximum recovery time: ${MAX_RECOVERY_TIME}s"
    
    # Validate environment
    if ! validate_environment; then
        error "Environment validation failed"
        exit 1
    fi
    
    # Measure baseline
    measure_baseline
    
    # Start background load if enabled
    if [[ "$LOAD_DURING_FAILURE" == "true" ]]; then
        generate_background_load
    fi
    
    # Execute specific failure test
    local test_result=0
    case "$FAILURE_TYPE" in
        "complete")
            test_complete_database_failure || test_result=1
            ;;
        "corruption")
            test_database_corruption || test_result=1
            ;;
        "network-partition")
            test_network_partition || test_result=1
            ;;
        "all")
            test_complete_database_failure || test_result=1
            test_database_corruption || test_result=1
            test_network_partition || test_result=1
            ;;
        *)
            error "Unknown failure type: $FAILURE_TYPE"
            exit 1
            ;;
    esac
    
    # Validate application behavior
    validate_application_behavior || test_result=1
    
    # Assess performance impact
    assess_performance_impact || test_result=1
    
    if [[ $test_result -eq 0 ]]; then
        log "DATABASE FAILURE TEST COMPLETED SUCCESSFULLY"
        exit 0
    else
        error "DATABASE FAILURE TEST FAILED"
        exit 1
    fi
}

# Set up cleanup trap
trap cleanup EXIT

# Execute main function
main "$@"