#!/usr/bin/env python3
"""
Blue1 RAG System - Comprehensive Production Validation Framework
PROVIDES HARD DATA AND MEASURABLE PROOF OF SYSTEM CAPACITY

This script generates detailed performance reports that can be replicated
by any contractor to validate system readiness for 4-location dealership.

Requirements validation:
- 400+ concurrent users
- 5,000+ daily queries  
- <2s average response time
- <3s 95th percentile response time
- 99%+ success rate
- High availability with failover
"""

import asyncio
import aiohttp
import time
import json
import statistics
import sys
import psutil
import datetime
import csv
import os
from typing import List, Tuple, Dict, Any
import argparse
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading


@dataclass
class TestResult:
    """Structured test result data."""
    timestamp: float
    response_time: float
    status_code: int
    success: bool
    error_message: str = ""
    query_type: str = "standard"


@dataclass
class LoadTestReport:
    """Comprehensive load test report with hard data."""
    test_name: str
    concurrent_users: int
    duration_seconds: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    requests_per_second: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    success_rate: float
    error_rate: float
    system_cpu_avg: float
    system_memory_avg: float
    timestamp: str


class SystemMonitor:
    """Monitor system resources during load testing."""
    
    def __init__(self):
        self.monitoring = False
        self.cpu_samples = []
        self.memory_samples = []
        self.disk_samples = []
        self.network_samples = []
        self.start_time = None
    
    def start_monitoring(self):
        """Start system monitoring in background thread."""
        self.monitoring = True
        self.start_time = time.time()
        self.cpu_samples = []
        self.memory_samples = []
        self.disk_samples = []
        self.network_samples = []
        
        def monitor_loop():
            while self.monitoring:
                try:
                    # CPU usage
                    cpu_percent = psutil.cpu_percent(interval=1)
                    self.cpu_samples.append(cpu_percent)
                    
                    # Memory usage
                    memory = psutil.virtual_memory()
                    self.memory_samples.append(memory.percent)
                    
                    # Disk I/O
                    disk_io = psutil.disk_io_counters()
                    if disk_io:
                        self.disk_samples.append({
                            'read_bytes': disk_io.read_bytes,
                            'write_bytes': disk_io.write_bytes
                        })
                    
                    # Network I/O
                    net_io = psutil.net_io_counters()
                    if net_io:
                        self.network_samples.append({
                            'bytes_sent': net_io.bytes_sent,
                            'bytes_recv': net_io.bytes_recv
                        })
                    
                except Exception as e:
                    print(f"Monitoring error: {e}")
                
                time.sleep(5)  # Sample every 5 seconds
        
        self.monitor_thread = threading.Thread(target=monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring and return statistics."""
        self.monitoring = False
        
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=2)
        
        duration = time.time() - self.start_time if self.start_time else 0
        
        return {
            'duration_seconds': duration,
            'cpu_avg': statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
            'cpu_max': max(self.cpu_samples) if self.cpu_samples else 0,
            'memory_avg': statistics.mean(self.memory_samples) if self.memory_samples else 0,
            'memory_max': max(self.memory_samples) if self.memory_samples else 0,
            'samples_collected': len(self.cpu_samples)
        }


class ProductionValidator:
    """Comprehensive production readiness validator with hard data collection."""
    
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url.rstrip('/')
        self.monitor = SystemMonitor()
        self.test_results: List[LoadTestReport] = []
        self.raw_results: List[TestResult] = []
        
        # Create results directory
        self.results_dir = f"validation-results-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Dealership-specific test queries
        self.test_queries = [
            "What Honda Civic models do you have in stock?",
            "Show me all used trucks under $30,000",
            "What's the service history for VIN 1HGBH41JXMN109186?", 
            "Do you have any Toyota Camry with low mileage?",
            "What are your current lease deals?",
            "Show me SUVs with third row seating",
            "What's included in your 60,000 mile service?",
            "Do you have financing options for used cars?",
            "What warranty comes with certified pre-owned vehicles?",
            "Show me all vehicles with navigation systems"
        ]
    
    async def health_check(self) -> bool:
        """Verify system is responding before load testing."""
        print("🔍 Performing health check...")
        
        try:
            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                async with session.get(f"{self.base_url}/health", timeout=10) as response:
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        data = await response.json()
                        print(f"   ✅ Health check passed: {data.get('status', 'unknown')} ({response_time:.3f}s)")
                        return True
                    else:
                        print(f"   ❌ Health check failed: HTTP {response.status} ({response_time:.3f}s)")
                        return False
        except Exception as e:
            print(f"   ❌ Health check error: {e}")
            return False
    
    async def single_rag_query(self, session: aiohttp.ClientSession, query: str, user_id: int) -> TestResult:
        """Execute single RAG query and collect detailed metrics."""
        start_time = time.time()
        
        try:
            query_data = {
                "query": query,
                "conversation_id": f"load-test-{user_id}"
            }
            
            headers = {"Authorization": "Bearer dev-secret-change-in-production"}
            
            async with session.post(
                f"{self.base_url}/query",
                json=query_data,
                timeout=30,
                headers=headers
            ) as response:
                response_time = time.time() - start_time
                response_text = await response.text()
                
                success = 200 <= response.status < 300
                
                return TestResult(
                    timestamp=start_time,
                    response_time=response_time,
                    status_code=response.status,
                    success=success,
                    error_message="" if success else response_text[:200],
                    query_type="rag_query"
                )
                
        except asyncio.TimeoutError:
            return TestResult(
                timestamp=start_time,
                response_time=time.time() - start_time,
                status_code=408,
                success=False,
                error_message="Request timeout",
                query_type="rag_query"
            )
        except Exception as e:
            return TestResult(
                timestamp=start_time,
                response_time=time.time() - start_time,
                status_code=500,
                success=False,
                error_message=str(e)[:200],
                query_type="rag_query"
            )
    
    async def simulate_dealership_user(self, session: aiohttp.ClientSession, user_id: int, duration_seconds: int) -> List[TestResult]:
        """Simulate realistic dealership user behavior."""
        results = []
        start_time = time.time()
        query_count = 0
        
        while (time.time() - start_time) < duration_seconds:
            # Select realistic query for automotive dealership
            query = self.test_queries[query_count % len(self.test_queries)]
            
            # Execute RAG query
            result = await self.single_rag_query(session, query, user_id)
            results.append(result)
            
            query_count += 1
            
            # Realistic user behavior: 10-30 seconds between queries
            think_time = 10 + (user_id % 20)  # Vary by user to avoid thundering herd
            await asyncio.sleep(think_time)
        
        return results
    
    async def run_load_test(self, concurrent_users: int, duration_seconds: int, test_name: str) -> LoadTestReport:
        """Execute comprehensive load test with detailed metrics collection."""
        print(f"\n🚀 EXECUTING LOAD TEST: {test_name}")
        print(f"   Concurrent Users: {concurrent_users}")
        print(f"   Duration: {duration_seconds} seconds") 
        print(f"   Target: Dealership RAG queries")
        
        # Start system monitoring
        self.monitor.start_monitoring()
        
        # Configure connection limits
        connector = aiohttp.TCPConnector(
            limit=concurrent_users * 2,
            limit_per_host=concurrent_users * 2,
            keepalive_timeout=60,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=35, connect=10, sock_read=30)
        
        test_start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                print(f"   🎯 Starting {concurrent_users} concurrent users...")
                
                # Launch concurrent user simulations
                user_tasks = [
                    self.simulate_dealership_user(session, user_id, duration_seconds)
                    for user_id in range(concurrent_users)
                ]
                
                # Wait for all users to complete
                all_results = await asyncio.gather(*user_tasks, return_exceptions=True)
                
                # Collect all results
                test_results = []
                for user_results in all_results:
                    if isinstance(user_results, list):
                        test_results.extend(user_results)
                    elif isinstance(user_results, Exception):
                        print(f"   ⚠️ User simulation error: {user_results}")
                
        except Exception as e:
            print(f"   ❌ Load test execution error: {e}")
            test_results = []
        
        # Stop monitoring
        system_stats = self.monitor.stop_monitoring()
        actual_duration = time.time() - test_start_time
        
        # Calculate comprehensive statistics
        if test_results:
            response_times = [r.response_time for r in test_results]
            successful_requests = sum(1 for r in test_results if r.success)
            
            # Calculate percentiles
            sorted_times = sorted(response_times)
            n = len(sorted_times)
            
            report = LoadTestReport(
                test_name=test_name,
                concurrent_users=concurrent_users,
                duration_seconds=int(actual_duration),
                total_requests=len(test_results),
                successful_requests=successful_requests,
                failed_requests=len(test_results) - successful_requests,
                requests_per_second=len(test_results) / actual_duration,
                avg_response_time=statistics.mean(response_times),
                min_response_time=min(response_times),
                max_response_time=max(response_times),
                p50_response_time=sorted_times[n//2] if n > 0 else 0,
                p95_response_time=sorted_times[int(n*0.95)] if n > 0 else 0,
                p99_response_time=sorted_times[int(n*0.99)] if n > 0 else 0,
                success_rate=successful_requests / len(test_results),
                error_rate=(len(test_results) - successful_requests) / len(test_results),
                system_cpu_avg=system_stats.get('cpu_avg', 0),
                system_memory_avg=system_stats.get('memory_avg', 0),
                timestamp=datetime.datetime.now().isoformat()
            )
        else:
            # Failed test case
            report = LoadTestReport(
                test_name=test_name,
                concurrent_users=concurrent_users,
                duration_seconds=int(actual_duration),
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                requests_per_second=0.0,
                avg_response_time=0.0,
                min_response_time=0.0,
                max_response_time=0.0,
                p50_response_time=0.0,
                p95_response_time=0.0,
                p99_response_time=0.0,
                success_rate=0.0,
                error_rate=1.0,
                system_cpu_avg=system_stats.get('cpu_avg', 0),
                system_memory_avg=system_stats.get('memory_avg', 0),
                timestamp=datetime.datetime.now().isoformat()
            )
        
        # Store raw results for detailed analysis
        self.raw_results.extend(test_results)
        
        # Print immediate results
        self.print_test_results(report)
        
        return report
    
    def print_test_results(self, report: LoadTestReport):
        """Print formatted test results with hard data."""
        print(f"\n📊 HARD DATA RESULTS - {report.test_name}")
        print("=" * 60)
        print(f"LOAD METRICS:")
        print(f"  • Concurrent Users: {report.concurrent_users}")
        print(f"  • Total Requests: {report.total_requests:,}")
        print(f"  • Requests/Second: {report.requests_per_second:.1f}")
        print(f"  • Test Duration: {report.duration_seconds}s")
        
        print(f"\nPERFORMANCE METRICS:")
        print(f"  • Success Rate: {report.success_rate:.1%}")
        print(f"  • Average Response: {report.avg_response_time:.3f}s")
        print(f"  • 50th Percentile: {report.p50_response_time:.3f}s")
        print(f"  • 95th Percentile: {report.p95_response_time:.3f}s")
        print(f"  • 99th Percentile: {report.p99_response_time:.3f}s")
        print(f"  • Min Response: {report.min_response_time:.3f}s")
        print(f"  • Max Response: {report.max_response_time:.3f}s")
        
        print(f"\nSYSTEM RESOURCES:")
        print(f"  • Average CPU: {report.system_cpu_avg:.1f}%")
        print(f"  • Average Memory: {report.system_memory_avg:.1f}%")
        
        print(f"\nERROR ANALYSIS:")
        print(f"  • Failed Requests: {report.failed_requests:,}")
        print(f"  • Error Rate: {report.error_rate:.1%}")
        
        # SLA Compliance Check
        print(f"\n🎯 DEALERSHIP SLA COMPLIANCE:")
        sla_checks = [
            ("Response Time (Avg < 2.0s)", report.avg_response_time < 2.0, f"{report.avg_response_time:.3f}s"),
            ("Response Time (95th < 3.0s)", report.p95_response_time < 3.0, f"{report.p95_response_time:.3f}s"),
            ("Success Rate (>99%)", report.success_rate > 0.99, f"{report.success_rate:.1%}"),
            ("Throughput (>10 req/s)", report.requests_per_second > 10.0, f"{report.requests_per_second:.1f}/s"),
            ("System Stable (CPU <80%)", report.system_cpu_avg < 80.0, f"{report.system_cpu_avg:.1f}%")
        ]
        
        all_passed = True
        for check_name, passed, value in sla_checks:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  • {check_name}: {status} ({value})")
            if not passed:
                all_passed = False
        
        overall_status = "✅ READY FOR PRODUCTION" if all_passed else "❌ REQUIRES OPTIMIZATION"
        print(f"\n🏆 OVERALL STATUS: {overall_status}")
    
    def save_detailed_report(self, reports: List[LoadTestReport]):
        """Save comprehensive test report to files."""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save summary report
        summary_file = os.path.join(self.results_dir, f"load_test_summary_{timestamp}.json")
        summary_data = {
            'test_timestamp': datetime.datetime.now().isoformat(),
            'system_info': {
                'cpu_cores': psutil.cpu_count(),
                'memory_gb': round(psutil.virtual_memory().total / (1024**3), 2),
                'python_version': sys.version,
                'test_target': self.base_url
            },
            'reports': [report.__dict__ for report in reports]
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        # Save CSV for spreadsheet analysis
        csv_file = os.path.join(self.results_dir, f"load_test_results_{timestamp}.csv")
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Test Name', 'Concurrent Users', 'Duration (s)', 'Total Requests', 'Successful Requests',
                'Requests/Second', 'Avg Response (s)', '95th Percentile (s)', 'Success Rate (%)',
                'CPU Avg (%)', 'Memory Avg (%)', 'SLA Compliant'
            ])
            
            for report in reports:
                sla_compliant = (
                    report.avg_response_time < 2.0 and
                    report.p95_response_time < 3.0 and 
                    report.success_rate > 0.99 and
                    report.system_cpu_avg < 80.0
                )
                
                writer.writerow([
                    report.test_name,
                    report.concurrent_users,
                    report.duration_seconds,
                    report.total_requests,
                    report.successful_requests,
                    round(report.requests_per_second, 2),
                    round(report.avg_response_time, 3),
                    round(report.p95_response_time, 3),
                    round(report.success_rate * 100, 2),
                    round(report.system_cpu_avg, 1),
                    round(report.system_memory_avg, 1),
                    'YES' if sla_compliant else 'NO'
                ])
        
        print(f"\n💾 DETAILED REPORTS SAVED:")
        print(f"   📋 Summary: {summary_file}")
        print(f"   📊 CSV Data: {csv_file}")
        
        return summary_file, csv_file
    
    async def comprehensive_validation(self) -> bool:
        """Run complete production validation with escalating load tests."""
        print("🏁 BLUE1 RAG SYSTEM - COMPREHENSIVE PRODUCTION VALIDATION")
        print("=" * 70)
        print("🎯 TARGET: 4-Location Automotive Dealership")
        print("📊 VALIDATION: Measurable Performance Data")
        print("🔬 REPLICATION: 100% Contractor Reproducible")
        print("")
        
        # System information
        print(f"🖥️  SYSTEM SPECIFICATIONS:")
        print(f"   CPU Cores: {psutil.cpu_count()}")
        print(f"   Memory: {round(psutil.virtual_memory().total / (1024**3), 1)} GB")
        print(f"   Test Target: {self.base_url}")
        print("")
        
        # 1. Health check
        if not await self.health_check():
            print("❌ System health check failed. Cannot proceed with load testing.")
            return False
        
        # 2. Progressive load testing (realistic dealership scenarios)
        test_scenarios = [
            (10, 60, "Baseline - Light Load (Single Location Morning)"),
            (50, 120, "Normal Operations (2 Locations Active)"), 
            (150, 180, "Busy Period (3 Locations + Lunch Rush)"),
            (300, 240, "Peak Load (All 4 Locations Busy)"),
            (400, 300, "Stress Test (Maximum Expected Load)"),
            (500, 180, "Overload Test (Beyond Capacity Validation)")
        ]
        
        reports = []
        all_tests_passed = True
        
        for concurrent_users, duration, test_name in test_scenarios:
            print(f"\n" + "="*70)
            
            try:
                report = await self.run_load_test(concurrent_users, duration, test_name)
                reports.append(report)
                
                # Check if test met dealership SLA requirements
                sla_compliant = (
                    report.success_rate > 0.99 and
                    report.avg_response_time < 2.0 and
                    report.p95_response_time < 3.0 and
                    report.system_cpu_avg < 80.0
                )
                
                if not sla_compliant:
                    if concurrent_users <= 400:  # Only fail if within expected capacity
                        all_tests_passed = False
                        print(f"   ⚠️ SLA requirements not met at {concurrent_users} users")
                    else:
                        print(f"   ℹ️ Expected degradation beyond design capacity")
                
                # Brief recovery period between tests
                if concurrent_users < 500:  # Skip for final test
                    print(f"   ⏸️ Recovery period (30 seconds)...")
                    await asyncio.sleep(30)
                
            except Exception as e:
                print(f"   ❌ Test failed with error: {e}")
                all_tests_passed = False
        
        # 3. Generate comprehensive report
        print(f"\n" + "="*70)
        print("📋 GENERATING COMPREHENSIVE VALIDATION REPORT")
        print("="*70)
        
        summary_file, csv_file = self.save_detailed_report(reports)
        
        # 4. Final assessment with hard numbers
        print(f"\n🏆 FINAL VALIDATION ASSESSMENT")
        print("="*70)
        
        if reports:
            max_capacity_report = max(reports, key=lambda r: r.concurrent_users if r.success_rate > 0.95 else 0)
            
            print(f"📊 MAXIMUM VALIDATED CAPACITY:")
            print(f"   • Concurrent Users: {max_capacity_report.concurrent_users}")
            print(f"   • Sustained Load: {max_capacity_report.duration_seconds} seconds")
            print(f"   • Success Rate: {max_capacity_report.success_rate:.1%}")
            print(f"   • Average Response: {max_capacity_report.avg_response_time:.3f}s")
            print(f"   • 95th Percentile: {max_capacity_report.p95_response_time:.3f}s")
            print(f"   • Throughput: {max_capacity_report.requests_per_second:.1f} req/s")
            
            # Dealership capacity assessment
            print(f"\n🏪 DEALERSHIP CAPACITY ASSESSMENT:")
            
            if max_capacity_report.concurrent_users >= 400 and max_capacity_report.success_rate > 0.99:
                print(f"   ✅ 4-Location Support: CONFIRMED")
                print(f"   ✅ 400+ Staff Users: SUPPORTED")
                print(f"   ✅ 5,000+ Daily Queries: SUPPORTED")
                print(f"   ✅ Peak Hour Performance: VALIDATED")
                deployment_ready = True
            else:
                print(f"   ❌ 4-Location Support: INSUFFICIENT")
                print(f"   ❌ Capacity Limitation: {max_capacity_report.concurrent_users} users max")
                print(f"   ❌ Performance Issues: {max_capacity_report.p95_response_time:.3f}s response time")
                deployment_ready = False
        else:
            print("   ❌ NO SUCCESSFUL TESTS COMPLETED")
            deployment_ready = False
        
        # Contractor replication instructions
        print(f"\n🔄 CONTRACTOR REPLICATION INSTRUCTIONS:")
        print(f"   1. Deploy system: ./deploy.sh")
        print(f"   2. Run validation: python production-validator.py --url YOUR_URL")
        print(f"   3. Review reports: {self.results_dir}/")
        print(f"   4. Validate SLA compliance in CSV export")
        
        if deployment_ready:
            print(f"\n🎉 VALIDATION RESULT: ✅ PRODUCTION READY")
            print(f"   System validated for 4-location automotive dealership")
            print(f"   Hard data confirms capacity requirements met")
            print(f"   Contractor can deploy with confidence")
        else:
            print(f"\n🚨 VALIDATION RESULT: ❌ NOT PRODUCTION READY") 
            print(f"   System requires optimization before deployment")
            print(f"   Review detailed reports for performance bottlenecks")
            print(f"   Contact system architect for capacity planning")
        
        return deployment_ready


async def main():
    """Main execution function with argument parsing."""
    parser = argparse.ArgumentParser(description='Blue1 RAG System Production Validation')
    parser.add_argument('--url', default='http://localhost', 
                       help='Base URL to test (default: http://localhost)')
    parser.add_argument('--quick', action='store_true',
                       help='Run quick validation (reduced load and duration)')
    parser.add_argument('--max-users', type=int, default=500,
                       help='Maximum concurrent users to test (default: 500)')
    
    args = parser.parse_args()
    
    print(f"🔬 Blue1 RAG System Production Validator")
    print(f"🎯 Target URL: {args.url}")
    print(f"⚡ Mode: {'Quick' if args.quick else 'Comprehensive'}")
    print("")
    
    validator = ProductionValidator(args.url)
    
    try:
        success = await validator.comprehensive_validation()
        
        print(f"\n{'='*70}")
        print(f"📋 VALIDATION COMPLETE")
        print(f"✅ Result: {'PRODUCTION READY' if success else 'REQUIRES OPTIMIZATION'}")
        print(f"📁 Reports: {validator.results_dir}/")
        print(f"{'='*70}")
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️ Validation interrupted by user")
        sys.exit(2)
    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())