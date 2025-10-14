# 🏗️ BLUE1 RAG SYSTEM - PRODUCTION REQUIREMENTS
## Exact Hardware & Infrastructure Specifications for 4-Location Dealership

---

## 📊 VALIDATED CAPACITY REQUIREMENTS

### **Target Load (4 Locations):**
- **Staff Users**: 400 concurrent (100 per location)
- **Daily Queries**: 5,000+ automotive queries
- **Peak Load**: 300-400 concurrent during busy hours
- **Response Time SLA**: <2s average, <3s 95th percentile
- **Uptime SLA**: 99.9% during business hours

---

## 💻 MINIMUM HARDWARE REQUIREMENTS

### **Production Server Specifications:**

#### **CPU Requirements:**
- **Minimum**: 16 vCPUs (8 physical cores)
- **Recommended**: 24 vCPUs (12 physical cores)
- **Optimal**: 32 vCPUs (16 physical cores)
- **Architecture**: x86_64 (Intel Xeon or AMD EPYC)

#### **Memory Requirements:**
- **Minimum**: 32 GB RAM
- **Recommended**: 64 GB RAM  
- **Optimal**: 128 GB RAM
- **Type**: DDR4-3200 or better

#### **Storage Requirements:**
- **System Drive**: 100 GB SSD (OS and applications)
- **Data Drive**: 500 GB SSD (databases, logs, backups)
- **Performance**: >10,000 IOPS, <1ms latency
- **Backup Storage**: 1 TB (30 days retention)

#### **Network Requirements:**
- **Bandwidth**: 1 Gbps dedicated
- **Latency**: <10ms to DMS providers
- **Ports**: 80, 443, 22, 9090, 3000, 5432, 6379, 9200

---

## 🌐 CLOUD INFRASTRUCTURE OPTIONS

### **AWS Configuration:**