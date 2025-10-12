#!/usr/bin/env python3
"""
System validation script - Run before deployment or demo.
Checks all dependencies, files, and configurations.
"""

import sys
import os
from pathlib import Path
import importlib.util


def print_header(text):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print('='*70)


def check_mark(passed):
    """Return check mark or X."""
    return "" if passed else ""


def check_python_version():
    """Check Python version."""
    print_header("Python Version Check")
    version = sys.version_info
    required = (3, 12)
    
    passed = version >= required
    print(f"{check_mark(passed)} Python {version.major}.{version.minor}.{version.micro}")
    if not passed:
        print(f"   ️  Python 3.12+ required, found {version.major}.{version.minor}")
    return passed


def check_required_packages():
    """Check if requirements.txt is valid and properly configured."""
    print_header("Requirements Configuration Check")
    
    requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print("{check_mark(False)} requirements.txt not found")
        return False
    
    print(f"{check_mark(True)} requirements.txt exists")
    
    # Parse requirements.txt
    with open(requirements_file) as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    required_core_packages = [
        'langchain', 'anthropic', 'voyageai', 'cohere', 'pinecone-client',
        'fastapi', 'uvicorn', 'redis', 'celery', 'pytest', 'pydantic'
    ]
    
    found_packages = set()
    for line in lines:
        package_name = line.split('==')[0].split('>=')[0].split('[')[0].strip()
        found_packages.add(package_name)
    
    results = []
    for package in required_core_packages:
        found = package in found_packages
        print(f"{check_mark(found)} {package:25s} {'specified' if found else 'MISSING'}")
        results.append(found)
    
    # Check version pinning
    pinned = [line for line in lines if '==' in line]
    pinned_ratio = len(pinned) / len(lines) if lines else 0
    print(f"\n{check_mark(pinned_ratio > 0.9)} Version pinning: {len(pinned)}/{len(lines)} packages ({pinned_ratio*100:.0f}%)")
    results.append(pinned_ratio > 0.9)
    
    return all(results)


def check_project_structure():
    """Check if all required files and directories exist."""
    print_header("Project Structure Check")
    
    required_paths = [
        "src/__init__.py",
        "src/config.py",
        "src/models.py",
        "src/agent.py",
        "src/app.py",
        "src/ingest.py",
        "src/embed.py",
        "src/retrieve.py",
        "src/generate.py",
        "src/tasks.py",
        "src/dms/__init__.py",
        "src/dms/base.py",
        "src/dms/mock_adapter.py",
        "src/dms/cdk_adapter.py",
        "src/dms/reynolds_adapter.py",
        "tests/conftest.py",
        "tests/test_ingest.py",
        "tests/test_retrieve.py",
        "tests/test_agent.py",
        "data/sample_inventory.json",
        "data/faqs.txt",
        "docs/API.md",
        "docs/ARCHITECTURE.md",
        "README.md",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
    ]
    
    results = []
    for path in required_paths:
        exists = Path(path).exists()
        print(f"{check_mark(exists)} {path}")
        results.append(exists)
    
    return all(results)


def check_environment_config():
    """Check environment configuration."""
    print_header("Environment Configuration Check")
    
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    results = []
    
    # Check if .env.example exists
    passed = env_example.exists()
    print(f"{check_mark(passed)} .env.example exists")
    results.append(passed)
    
    # Check if .env exists (optional for demo)
    env_exists = env_file.exists()
    print(f"{'' if env_exists else '️ '} .env file {'exists' if env_exists else 'not found (using defaults)'}")
    
    # Check required env vars from .env.example
    if env_example.exists():
        with open(env_example) as f:
            example_content = f.read()
        
        required_vars = [
            "ANTHROPIC_API_KEY",
            "VOYAGE_API_KEY",
            "COHERE_API_KEY",
            "PINECONE_API_KEY",
        ]
        
        for var in required_vars:
            in_example = var in example_content
            print(f"{check_mark(in_example)} {var} in .env.example")
            results.append(in_example)
    
    return all(results)


def check_imports():
    """Check if main modules can be imported."""
    print_header("Module Import Check")
    
    sys.path.insert(0, str(Path.cwd()))
    
    modules = [
        ("src.config", "Configuration"),
        ("src.models", "Data Models"),
        ("src.dms.base", "DMS Base"),
        ("src.dms.mock_adapter", "Mock DMS"),
    ]
    
    results = []
    for module, name in modules:
        try:
            __import__(module)
            print(f" {name:25s} imports successfully")
            results.append(True)
        except Exception as e:
            print(f" {name:25s} import failed: {str(e)[:50]}")
            results.append(False)
    
    return all(results)


def check_docker_files():
    """Check Docker configuration."""
    print_header("Docker Configuration Check")
    
    dockerfile = Path("Dockerfile")
    compose = Path("docker-compose.yml")
    
    results = []
    
    # Check Dockerfile
    passed = dockerfile.exists()
    print(f"{check_mark(passed)} Dockerfile exists")
    results.append(passed)
    
    if passed:
        with open(dockerfile) as f:
            content = f.read()
        has_python = "python" in content.lower()
        has_fastapi = "fastapi" in content.lower() or "uvicorn" in content.lower()
        print(f"  {check_mark(has_python)} Contains Python setup")
        print(f"  {check_mark(has_fastapi)} Contains FastAPI setup")
        results.extend([has_python, has_fastapi])
    
    # Check docker-compose.yml
    passed = compose.exists()
    print(f"{check_mark(passed)} docker-compose.yml exists")
    results.append(passed)
    
    if passed:
        with open(compose) as f:
            content = f.read()
        has_services = "services:" in content
        has_redis = "redis" in content.lower()
        print(f"  {check_mark(has_services)} Defines services")
        print(f"  {check_mark(has_redis)} Includes Redis")
        results.extend([has_services, has_redis])
    
    return all(results)


def check_documentation():
    """Check documentation completeness."""
    print_header("Documentation Check")
    
    docs = [
        ("README.md", "Project README"),
        ("docs/API.md", "API Documentation"),
        ("docs/ARCHITECTURE.md", "Architecture Docs"),
        ("CONTRIBUTING.md", "Contributing Guide"),
        ("CHANGELOG.md", "Changelog"),
    ]
    
    results = []
    for path, name in docs:
        exists = Path(path).exists()
        print(f"{check_mark(exists)} {name:30s} {path}")
        results.append(exists)
        
        if exists:
            size = Path(path).stat().st_size
            has_content = size > 500
            print(f"  {'' if has_content else '️ '} Size: {size} bytes {'(good)' if has_content else '(too small?)'}")
    
    return all(results)


def check_tests():
    """Check test suite."""
    print_header("Test Suite Check")
    
    test_files = list(Path("tests").glob("test_*.py"))
    
    print(f" Found {len(test_files)} test files")
    for test in test_files:
        print(f"   {test.name}")
    
    # Check if conftest exists
    conftest = Path("tests/conftest.py")
    passed = conftest.exists()
    print(f"{check_mark(passed)} conftest.py exists (test fixtures)")
    
    return passed and len(test_files) >= 5


def check_git_repository():
    """Check git repository integrity."""
    print_header("Git Repository Integrity Check")
    
    import subprocess
    
    results = []
    
    # Check if in git repo
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, check=True)
        print(f"{check_mark(True)} Valid git repository")
        results.append(True)
    except:
        print(f"{check_mark(False)} Not a git repository")
        results.append(False)
        return False
    
    # Check for tags
    try:
        tags = subprocess.run(["git", "tag"], capture_output=True, text=True)
        has_tags = len(tags.stdout.strip()) > 0
        tag_list = tags.stdout.strip()
        print(f"{check_mark(has_tags)} Release tags: {tag_list if has_tags else 'none'}")
        results.append(has_tags)
    except:
        print(f"{check_mark(False)} No release tags")
        results.append(False)
    
    # Check commit count
    try:
        commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True)
        commit_count = int(commits.stdout.strip())
        has_commits = commit_count >= 10
        print(f"{check_mark(has_commits)} Commits: {commit_count} (target: >=10)")
        results.append(has_commits)
    except:
        print(f"{check_mark(False)} Cannot count commits")
        results.append(False)
    
    # Check working directory is clean
    try:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        is_clean = len(status.stdout.strip()) == 0
        print(f"{check_mark(is_clean)} Working directory: {'clean' if is_clean else 'uncommitted changes'}")
        results.append(is_clean)
    except:
        results.append(True)
    
    return all(results)


def check_security_files():
    """Check security and governance files."""
    print_header("Security & Governance Files Check")
    
    security_files = [
        ("SECURITY.md", "Security policy"),
        ("CONTRIBUTORS.md", "Contributors list"),
        (".github/pull_request_template.md", "PR template"),
        (".github/ISSUE_TEMPLATE/bug_report.md", "Bug template"),
        (".pre-commit-config.yaml", "Pre-commit hooks"),
        ("pyproject.toml", "Project config"),
    ]
    
    results = []
    for file_path, description in security_files:
        exists = Path(file_path).exists()
        print(f"{check_mark(exists)} {file_path:45s} ({description})")
        results.append(exists)
    
    return all(results)


def generate_report():
    """Run all checks and generate report."""
    print("\n" + "="*70)
    print("  DEALERSHIP RAG SYSTEM - VALIDATION REPORT")
    print("="*70)
    
    checks = [
        ("Python Version", check_python_version),
        ("Requirements Configuration", check_required_packages),
        ("Project Structure", check_project_structure),
        ("Environment Configuration", check_environment_config),
        ("Module Imports", check_imports),
        ("Docker Configuration", check_docker_files),
        ("Documentation Quality", check_documentation),
        ("Test Suite Presence", check_tests),
        ("Git Repository Integrity", check_git_repository),
        ("Security Files Present", check_security_files),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n ERROR in {name}: {e}")
            results[name] = False
    
    # Final summary
    print("\n" + "="*70)
    print("  SUMMARY")
    print("="*70)
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    for name, passed in results.items():
        print(f"{check_mark(passed)} {name:30s} {'PASSED' if passed else 'FAILED'}")
    
    print("\n" + "="*70)
    percentage = (passed_count / total_count) * 100
    print(f"  Overall: {passed_count}/{total_count} checks passed ({percentage:.1f}%)")
    print("="*70)
    
    if passed_count == total_count:
        print("\n SYSTEM VALIDATION COMPLETE - ALL CHECKS PASSED!")
        print("   Ready for deployment and demonstration.")
        return 0
    else:
        print(f"\n️  {total_count - passed_count} CHECKS FAILED")
        print("   Please fix issues before deployment.")
        return 1


if __name__ == "__main__":
    exit_code = generate_report()
    sys.exit(exit_code)

