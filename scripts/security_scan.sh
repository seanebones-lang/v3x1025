#!/bin/bash
# Security scanning script for dependency vulnerabilities and code issues
# Run before deployment to production

set -e

echo "🔒 Security Scanning - Dealership RAG System"
echo "=============================================="
echo ""

# Check if tools are installed
if ! command -v bandit &> /dev/null; then
    echo "Installing Bandit (security linter)..."
    pip install bandit
fi

if ! command -v safety &> /dev/null; then
    echo "Installing Safety (dependency checker)..."
    pip install safety
fi

# Run Bandit - Python security linter
echo "📊 Running Bandit security linter..."
echo "--------------------------------------------"
bandit -r src/ -f screen || echo "⚠️  Bandit found potential issues"
echo ""

# Run Safety - Check dependencies for known vulnerabilities
echo "🔍 Checking dependencies for vulnerabilities..."
echo "--------------------------------------------"
safety check --json || echo "⚠️  Safety found vulnerable dependencies"
echo ""

# Additional security checks
echo "🔐 Additional Security Checks..."
echo "--------------------------------------------"

# Check for hardcoded secrets
echo "Checking for potential hardcoded secrets..."
grep -r "password\s*=\s*['\"]" src/ && echo "⚠️  Found potential hardcoded password" || echo "✅ No hardcoded passwords"
grep -r "api_key\s*=\s*['\"][^{]" src/ && echo "⚠️  Found potential hardcoded API key" || echo "✅ No hardcoded API keys"

# Check for .env in git
if git ls-files | grep -q "^\.env$"; then
    echo "❌ .env file is tracked in git!"
else
    echo "✅ .env file not tracked in git"
fi

# Check requirements for outdated packages
echo ""
echo "📦 Checking for outdated packages..."
echo "--------------------------------------------"
pip list --outdated || true

echo ""
echo "=============================================="
echo "✅ Security scan complete"
echo "Review any warnings above before deployment"
echo "=============================================="

