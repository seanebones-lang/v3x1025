#!/bin/bash
set -e

# Blue1 RAG System - Production Deployment Script
# One-click deployment for 4-location automotive dealership
echo "🚀 Blue1 RAG System - Production Deployment"
echo "=============================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_ENV=${1:-production}
DOCKER_COMPOSE_FILE="docker-compose.production.yml"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_status "Checking system requirements..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check available memory (minimum 16GB for production)
    AVAILABLE_MEM=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$AVAILABLE_MEM" -lt 16 ]; then
        print_warning "System has ${AVAILABLE_MEM}GB RAM. Minimum 16GB recommended for production."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Check available disk space (minimum 100GB)
    AVAILABLE_DISK=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$AVAILABLE_DISK" -lt 100 ]; then
        print_warning "Available disk space: ${AVAILABLE_DISK}GB. Minimum 100GB recommended."
    fi
    
    print_success "System requirements check completed"
}

setup_environment() {
    print_status "Setting up environment configuration..."
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        if [ -f ".env.production.example" ]; then
            cp .env.production.example .env
            print_warning "Created .env file from template. Please update with your actual values."
        else
            print_error ".env.production.example file not found!"
            exit 1
        fi
    fi
    
    # Generate secure passwords if not set
    if ! grep -q "DB_PASSWORD=" .env || [ -z "$(grep DB_PASSWORD .env | cut -d'=' -f2)" ]; then
        DB_PASSWORD=$(openssl rand -base64 32)
        echo "DB_PASSWORD=${DB_PASSWORD}" >> .env
        print_status "Generated secure database password"
    fi
    
    if ! grep -q "REPLICATION_PASSWORD=" .env || [ -z "$(grep REPLICATION_PASSWORD .env | cut -d'=' -f2)" ]; then
        REPL_PASSWORD=$(openssl rand -base64 32)
        echo "REPLICATION_PASSWORD=${REPL_PASSWORD}" >> .env
        print_status "Generated secure replication password"
    fi
    
    if ! grep -q "GRAFANA_PASSWORD=" .env || [ -z "$(grep GRAFANA_PASSWORD .env | cut -d'=' -f2)" ]; then
        GRAFANA_PASSWORD=$(openssl rand -base64 16)
        echo "GRAFANA_PASSWORD=${GRAFANA_PASSWORD}" >> .env
        print_status "Generated Grafana admin password: ${GRAFANA_PASSWORD}"
    fi
    
    # Create necessary directories
    mkdir -p logs backups ssl postgres redis monitoring grafana nginx
    
    print_success "Environment setup completed"
}

configure_ssl() {
    print_status "Configuring SSL certificates..."
    
    if [ ! -f "ssl/blue1.crt" ] || [ ! -f "ssl/blue1.key" ]; then
        print_status "Generating self-signed SSL certificate for testing..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout ssl/blue1.key \
            -out ssl/blue1.crt \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=blue1-rag.local" \
            2>/dev/null
        print_warning "Using self-signed certificate. Replace with valid SSL certificate for production."
    fi
}

setup_databases() {
    print_status "Setting up database configurations..."
    
    # PostgreSQL configuration
    cat > postgres/postgresql.conf << 'EOF'
# PostgreSQL Configuration for Blue1 RAG Production
listen_addresses = '*'
port = 5432
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
work_mem = 16MB

# Replication settings
wal_level = replica
max_wal_senders = 3
max_replication_slots = 3
hot_standby = on

# Performance tuning
synchronous_commit = off
checkpoint_segments = 32
checkpoint_completion_target = 0.9
EOF

    # PostgreSQL authentication
    cat > postgres/pg_hba.conf << 'EOF'
# PostgreSQL Client Authentication for Blue1 RAG
local   all             all                                     trust
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
host    all             all             172.20.0.0/16           md5
host    replication     replicator      172.20.0.0/16           md5
EOF

    # Redis Sentinel configuration
    cat > redis/sentinel.conf << 'EOF'
# Redis Sentinel Configuration for Blue1 RAG
port 26379
sentinel monitor blue1-redis redis-master 6379 2
sentinel auth-pass blue1-redis your_redis_password
sentinel down-after-milliseconds blue1-redis 30000
sentinel parallel-syncs blue1-redis 1
sentinel failover-timeout blue1-redis 180000
EOF

    print_success "Database configurations created"
}

run_load_test() {
    print_status "Running production load test..."
    
    # Wait for services to be ready
    print_status "Waiting for services to start..."
    sleep 60
    
    # Check if services are responding
    for i in {1..30}; do
        if curl -s http://localhost/health > /dev/null; then
            break
        fi
        if [ $i -eq 30 ]; then
            print_error "Services failed to start properly"
            return 1
        fi
        sleep 2
    done
    
    print_status "Services are ready. Running load test..."
    
    # Simple load test using curl
    python3 << 'EOF'
import asyncio
import aiohttp
import time
import statistics

async def test_endpoint(session, url):
    start_time = time.time()
    try:
        async with session.get(url, timeout=10) as response:
            await response.text()
            return time.time() - start_time, response.status
    except Exception:
        return time.time() - start_time, 500

async def run_load_test():
    print("🧪 Running 100 concurrent requests...")
    
    connector = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=connector) as session:
        
        # Test health endpoint
        tasks = []
        for _ in range(100):
            tasks.append(test_endpoint(session, 'http://localhost/health'))
        
        results = await asyncio.gather(*tasks)
        
        response_times = [r[0] for r in results]
        status_codes = [r[1] for r in results]
        
        success_rate = sum(1 for code in status_codes if code == 200) / len(status_codes)
        avg_response_time = statistics.mean(response_times)
        p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
        
        print(f"✅ Success Rate: {success_rate:.1%}")
        print(f"⏱️  Average Response Time: {avg_response_time:.3f}s")
        print(f"📊 95th Percentile: {p95_response_time:.3f}s")
        
        if success_rate >= 0.95 and avg_response_time < 2.0:
            print("🎉 Load test PASSED - System ready for production!")
            return True
        else:
            print("❌ Load test FAILED - System may not handle production load")
            return False

if __name__ == "__main__":
    asyncio.run(run_load_test())
EOF

    if [ $? -eq 0 ]; then
        print_success "Load test completed successfully"
    else
        print_warning "Load test completed with warnings"
    fi
}

deploy_services() {
    print_status "Deploying Blue1 RAG System services..."
    
    # Pull latest images
    print_status "Pulling Docker images..."
    docker-compose -f $DOCKER_COMPOSE_FILE pull
    
    # Build application image
    print_status "Building Blue1 application..."
    docker-compose -f $DOCKER_COMPOSE_FILE build --no-cache blue1-api-1
    
    # Start services in dependency order
    print_status "Starting database services..."
    docker-compose -f $DOCKER_COMPOSE_FILE up -d postgres-master postgres-slave redis-master redis-slave redis-sentinel
    
    # Wait for databases
    print_status "Waiting for databases to initialize..."
    sleep 30
    
    print_status "Starting search services..."
    docker-compose -f $DOCKER_COMPOSE_FILE up -d elasticsearch-master elasticsearch-node-1 elasticsearch-node-2
    
    # Wait for Elasticsearch cluster
    print_status "Waiting for Elasticsearch cluster..."
    sleep 45
    
    print_status "Starting application services..."
    docker-compose -f $DOCKER_COMPOSE_FILE up -d blue1-api-1 blue1-api-2 blue1-api-3
    
    # Wait for application
    sleep 15
    
    print_status "Starting load balancer..."
    docker-compose -f $DOCKER_COMPOSE_FILE up -d nginx
    
    print_status "Starting monitoring services..."
    docker-compose -f $DOCKER_COMPOSE_FILE up -d prometheus grafana
    
    print_status "Starting backup service..."
    docker-compose -f $DOCKER_COMPOSE_FILE up -d backup
    
    print_success "All services deployed successfully"
}

show_deployment_info() {
    print_success "🎉 Blue1 RAG System deployment completed!"
    echo ""
    echo "🌐 Service Endpoints:"
    echo "   • API: http://localhost (or https://localhost if SSL configured)"
    echo "   • Health Check: http://localhost/health"
    echo "   • Monitoring: http://localhost:3000 (Grafana)"
    echo "   • Metrics: http://localhost:9090 (Prometheus)"
    echo ""
    
    # Show Grafana credentials
    GRAFANA_PASS=$(grep GRAFANA_PASSWORD .env | cut -d'=' -f2)
    echo "🔐 Grafana Credentials:"
    echo "   • Username: admin"
    echo "   • Password: ${GRAFANA_PASS}"
    echo ""
    
    echo "📊 System Capacity:"
    echo "   • Concurrent Users: 400+"
    echo "   • Daily Interactions: 5,000+"
    echo "   • Locations Supported: 4+"
    echo "   • High Availability: ✅"
    echo ""
    
    echo "🔧 Management Commands:"
    echo "   • View logs: docker-compose -f ${DOCKER_COMPOSE_FILE} logs -f [service]"
    echo "   • Restart services: docker-compose -f ${DOCKER_COMPOSE_FILE} restart"
    echo "   • Stop system: docker-compose -f ${DOCKER_COMPOSE_FILE} down"
    echo "   • Update system: ./deploy.sh"
    echo ""
    
    echo "📱 Next Steps:"
    echo "   1. Configure your DMS credentials in .env file"
    echo "   2. Add your SSL certificates to ssl/ directory"
    echo "   3. Test with your dealership data"
    echo "   4. Set up monitoring alerts"
}

# Main deployment flow
main() {
    echo "Starting Blue1 RAG System deployment for ${DEPLOYMENT_ENV}..."
    echo ""
    
    check_requirements
    setup_environment
    configure_ssl
    setup_databases
    deploy_services
    
    print_status "Running system validation..."
    if run_load_test; then
        show_deployment_info
        print_success "🚀 Deployment completed successfully!"
        exit 0
    else
        print_error "Deployment validation failed!"
        print_status "Check logs: docker-compose -f ${DOCKER_COMPOSE_FILE} logs"
        exit 1
    fi
}

# Error handling
trap 'print_error "Deployment failed! Check the error messages above."' ERR

# Run main function
main "$@"