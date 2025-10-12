# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | Yes                |
| < 1.0   | No                 |

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Please report security vulnerabilities to:
- **Email:** seanebones@gmail.com
- **Subject:** [SECURITY] Dealership RAG Vulnerability Report

### What to Include

1. Type of vulnerability
2. Full paths of source files related to the manifestation
3. Location of affected source code (tag/branch/commit/URL)
4. Step-by-step instructions to reproduce
5. Proof-of-concept or exploit code (if possible)
6. Impact assessment

### Response Timeline

- Initial response: Within 48 hours
- Confirmation and assessment: Within 1 week
- Fix and disclosure: Coordinated with reporter

### Security Best Practices

**For Deployers:**
- Never commit `.env` files with real credentials
- Use environment variables for all secrets
- Enable rate limiting in production
- Implement API key rotation schedule
- Use HTTPS in production deployments
- Keep dependencies updated (run `safety check` regularly)
- Enable audit logging for compliance
- Implement network policies in Kubernetes
- Use secret management services (AWS Secrets Manager, HashiCorp Vault)

**For Contributors:**
- Run `bandit -r src/` before submitting PRs
- Run `safety check` to identify vulnerable dependencies
- Never hardcode credentials or API keys
- Sanitize user inputs in all endpoints
- Use parameterized queries for database access
- Follow OWASP Top 10 guidelines

## Known Security Considerations

1. **API Key Storage**: Use environment variables, never hardcode
2. **Input Validation**: All endpoints use Pydantic validation
3. **Rate Limiting**: Default 100 req/min per IP (configurable)
4. **File Uploads**: Validate file types and sizes in production
5. **SQL Injection**: Use parameterized queries via SQLAlchemy
6. **XSS Prevention**: Sanitize query inputs before processing
7. **CORS**: Configure `allow_origins` for production domains only

## Security Scanning

Automated security checks run in CI/CD:
- Bandit (Python security linter)
- Safety (dependency vulnerability checker)
- MyPy (type safety)

Run locally:
```bash
./scripts/security_scan.sh
```

## Dependency Updates

Monitor for security updates:
```bash
pip list --outdated
safety check --json
```

Update regularly and test thoroughly before deploying.

## Compliance

- **GDPR**: PII anonymization hooks available
- **SOC 2**: Audit logging can be enabled
- **HIPAA**: Not currently compliant (contact for healthcare use)
- **PCI DSS**: Not handling payment data directly

## Attribution

Security researchers who responsibly disclose vulnerabilities will be credited in CHANGELOG.md unless they prefer anonymity.

