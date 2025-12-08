# PyPI Setup Guide

## Setting Up PyPI Account and Publishing

### Step 1: Create PyPI Account

1. **Go to PyPI:**
   - Production: https://pypi.org/account/register/
   - TestPyPI (for testing): https://test.pypi.org/account/register/

2. **Register Account:**
   - Choose a username (e.g., `z-markus`)
   - Use your email address
   - Set a strong password
   - Verify your email

### Step 2: Enable Two-Factor Authentication (Recommended)

1. Log in to PyPI
2. Go to Account Settings → Security
3. Enable 2FA (Two-Factor Authentication)
4. Use an authenticator app (Google Authenticator, Authy, etc.)

### Step 3: Create API Token

1. **Go to Account Settings:**
   - https://pypi.org/manage/account/

2. **Create API Token:**
   - Scroll to "API tokens" section
   - Click "Add API token"
   - **Token name**: `PPTrans-GitHub-Actions` (or any descriptive name)
   - **Scope**: 
     - For entire account: Select "Entire account"
     - For specific project: Select "Project: ppt-translator"
   - Click "Add token"

3. **Copy the Token:**
   - ⚠️ **Important**: Copy the token immediately - you won't be able to see it again!
   - Format: `pypi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Step 4: Add Token to GitHub Secrets

1. **Go to GitHub Repository:**
   - Navigate to: https://github.com/Z-MarkUs/PPTrans

2. **Go to Settings:**
   - Click "Settings" tab
   - Click "Secrets and variables" → "Actions"

3. **Add Secret:**
   - Click "New repository secret"
   - **Name**: `PYPI_API_TOKEN`
   - **Value**: Paste your PyPI API token (`pypi-xxxxx...`)
   - Click "Add secret"

### Step 5: Verify Package Name Availability

Before publishing, check if your package name is available:

```bash
# Check if name is taken
curl https://pypi.org/pypi/ppt-translator/json

# If you get 404, the name is available!
# If you get package info, the name is taken
```

**Note:** Package names on PyPI are case-insensitive and must be unique. If `ppt-translator` is taken, you might need to use:
- `ppt-translator-tool`
- `pptrans`
- `powerpoint-translator`
- Or add your username: `z-markus-ppt-translator`

### Step 6: Test on TestPyPI First (Recommended)

Before publishing to production PyPI, test on TestPyPI:

1. **Create TestPyPI Account:**
   - Go to: https://test.pypi.org/account/register/
   - Register (can use same username as PyPI)

2. **Create TestPyPI API Token:**
   - Same process as Step 3, but on TestPyPI

3. **Add TestPyPI Token to GitHub:**
   - Add secret: `TEST_PYPI_API_TOKEN`

4. **Test Upload:**
   ```bash
   # Build package
   python -m build
   
   # Upload to TestPyPI
   twine upload --repository testpypi dist/*
   
   # Test installation
   pip install --index-url https://test.pypi.org/simple/ ppt-translator
   ```

### Step 7: Publish to Production PyPI

Once tested, publish to production:

**Manual Upload:**
```bash
# Build package
python -m build

# Upload to PyPI
twine upload dist/*
```

**Via GitHub Actions:**
- The workflow will automatically publish when you create a GitHub release
- Make sure `PYPI_API_TOKEN` secret is set in GitHub

### Step 8: Verify Publication

After publishing, verify your package:

1. **Check PyPI Page:**
   - https://pypi.org/project/ppt-translator/

2. **Test Installation:**
   ```bash
   pip install ppt-translator
   ppt-translator --help
   ```

## GitHub Actions Workflow

The `.github/workflows/release.yml` workflow will:

1. ✅ Build Python package when release is created
2. ✅ Check package with `twine check`
3. ✅ Upload to PyPI automatically (if `PYPI_API_TOKEN` is set)
4. ✅ Upload build artifacts to GitHub

**To trigger:**
- Create a GitHub release (manual or via `./release.sh`)
- Or manually trigger via "Actions" → "Release" → "Run workflow"

## Troubleshooting

### "Package name already exists"
- Choose a different name in `pyproject.toml` and `setup.py`
- Update `name = "ppt-translator"` to something unique

### "Invalid API token"
- Regenerate token on PyPI
- Update `PYPI_API_TOKEN` secret in GitHub
- Make sure token has correct scope

### "403 Forbidden"
- Check token permissions
- Verify token hasn't expired
- Ensure 2FA is properly configured

### "Package version already exists"
- Increment version in `pyproject.toml` and `setup.py`
- Update `version = "1.0.0"` to `version = "1.0.1"`

## Package Name Best Practices

- Use lowercase letters, numbers, hyphens, and underscores
- Keep it short and descriptive
- Check availability before publishing
- Avoid names that conflict with existing packages

## Security Notes

- ⚠️ **Never commit API tokens to git**
- ✅ Use GitHub Secrets for tokens
- ✅ Use project-scoped tokens when possible
- ✅ Rotate tokens periodically
- ✅ Enable 2FA on PyPI account

## Quick Reference

**Check package name:**
```bash
curl https://pypi.org/pypi/YOUR-PACKAGE-NAME/json
```

**Test on TestPyPI:**
```bash
twine upload --repository testpypi dist/*
```

**Publish to PyPI:**
```bash
twine upload dist/*
```

**Install from PyPI:**
```bash
pip install ppt-translator
```

