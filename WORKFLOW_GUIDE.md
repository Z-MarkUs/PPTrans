# GitHub Actions Workflow Guide

## Understanding the Workflow Flow

### Current Setup

The workflow (`.github/workflows/release.yml`) is configured to:
- **Trigger**: When a GitHub release is **created** (published)
- **Action**: Automatically build and publish to PyPI

### Order of Operations

**Correct Order:**
1. ✅ **Push workflow file to GitHub** (if not already pushed)
2. ✅ **Create GitHub release** (this triggers the workflow)
3. ✅ **Workflow runs automatically** (builds and publishes)

**Wrong Order:**
- ❌ Create release first, then push workflow → Workflow won't run for that release

## Step-by-Step Process

### Step 1: Ensure Workflow is Pushed to GitHub

```bash
# Check if workflow file exists locally
ls -la .github/workflows/release.yml

# Check if it's committed
git status .github/workflows/release.yml

# If not committed, commit and push
git add .github/workflows/release.yml
git commit -m "Add release workflow"
git push origin main
```

### Step 2: Verify Workflow is on GitHub

1. Go to your repository: https://github.com/Z-MarkUs/PPTrans
2. Click on **"Actions"** tab (top navigation)
3. You should see:
   - "Release" workflow listed
   - If you don't see it, the file might not be pushed yet

### Step 3: Set Up PyPI Token (One-Time)

Before creating a release, make sure `PYPI_API_TOKEN` is set:

1. Go to: https://github.com/Z-MarkUs/PPTrans/settings/secrets/actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token (`pypi-xxxxx...`)
5. Click "Add secret"

**Note:** The workflow will still run without this token, but it won't publish to PyPI (will show a warning).

### Step 4: Create Release (This Triggers Workflow)

**Option A: Using Script (Recommended)**
```bash
./release.sh
```

**Option B: Manual Release**
```bash
# 1. Tag the release
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# 2. Go to GitHub and create release
# https://github.com/Z-MarkUs/PPTrans/releases/new
```

**Option C: GitHub CLI**
```bash
gh release create v1.0.0 --title "v1.0.0" --notes "Release notes"
```

### Step 5: Watch Workflow Run

1. After creating release, go to **Actions** tab
2. You'll see the "Release" workflow running
3. Click on it to see progress
4. It will:
   - Build the package
   - Check with twine
   - Publish to PyPI (if token is set)
   - Upload artifacts

## Troubleshooting: "I don't see workflows"

### Problem 1: Workflow file not pushed

**Check:**
```bash
git status .github/workflows/release.yml
```

**Fix:**
```bash
git add .github/workflows/release.yml
git commit -m "Add release workflow"
git push origin main
```

### Problem 2: Looking in wrong place

**Where to look:**
- ✅ Correct: https://github.com/Z-MarkUs/PPTrans/actions
- ❌ Wrong: Local `.github` folder (that's just the file)

**Steps:**
1. Go to your GitHub repository
2. Click **"Actions"** tab (top navigation bar)
3. You should see workflows listed on the left sidebar

### Problem 3: Workflow file not in correct location

**Correct structure:**
```
.github/
  workflows/
    release.yml    ← Must be here
```

**Check:**
```bash
ls -la .github/workflows/
# Should show: release.yml
```

### Problem 4: Workflow not triggering

**Common causes:**
- Release was created before workflow was pushed
- Workflow file has syntax errors
- Branch protection rules blocking workflows

**Check workflow syntax:**
```bash
# GitHub Actions has a validator, but you can check YAML syntax
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

## Testing the Workflow

### Test Without Creating Release

You can manually trigger the workflow:

1. Go to: https://github.com/Z-MarkUs/PPTrans/actions
2. Click on "Release" workflow
3. Click "Run workflow" button (top right)
4. Select branch: `main`
5. Click "Run workflow"

This will run the workflow without needing a release.

### Test Locally First

Before relying on GitHub Actions, test locally:

```bash
# Build package
python -m build

# Check package
pip install twine
twine check dist/*

# Test upload to TestPyPI
twine upload --repository testpypi dist/*
```

## Workflow Status Indicators

When you go to Actions tab, you'll see:

- 🟡 **Yellow dot**: Workflow is running
- ✅ **Green checkmark**: Workflow succeeded
- ❌ **Red X**: Workflow failed
- ⚪ **Gray circle**: Workflow not run yet

## Quick Checklist

Before creating your first release:

- [ ] Workflow file exists: `.github/workflows/release.yml`
- [ ] Workflow file is committed and pushed to GitHub
- [ ] Can see "Release" workflow in Actions tab
- [ ] `PYPI_API_TOKEN` secret is set (optional but recommended)
- [ ] Package name is available on PyPI
- [ ] Version number is correct in `pyproject.toml` and `setup.py`

## Expected Workflow Behavior

When you create a release:

1. **Workflow starts automatically** (within seconds)
2. **Builds package** (~1-2 minutes)
3. **Validates package** (~10 seconds)
4. **Publishes to PyPI** (~30 seconds, if token set)
5. **Uploads artifacts** (~10 seconds)
6. **Total time**: ~2-3 minutes

## Verification

After workflow completes:

1. **Check PyPI:**
   - https://pypi.org/project/ppt-translator/
   - Should show your package

2. **Test Installation:**
   ```bash
   pip install ppt-translator
   ppt-translator --help
   ```

3. **Check GitHub Release:**
   - Go to Releases page
   - Your release should be there
   - Artifacts should be attached

