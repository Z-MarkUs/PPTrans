# Quick Start: Creating Your First Release

## The Correct Order

**✅ CORRECT ORDER:**
1. **Push workflow file to GitHub** (if not already there)
2. **Set up PyPI token** (one-time setup)
3. **Create release** → This triggers the workflow automatically
4. **Workflow runs** → Builds and publishes automatically

## Step-by-Step Instructions

### Step 1: Verify Workflow File is on GitHub

**Check locally:**
```bash
# Make sure workflow file exists
ls -la .github/workflows/release.yml

# Check if it's committed
git status .github/workflows/release.yml
```

**If not pushed yet:**
```bash
# Push to GitHub
git push origin main
```

**Verify on GitHub:**
1. Go to: https://github.com/Z-MarkUs/PPTrans
2. Click **"Actions"** tab (top navigation)
3. You should see **"Release"** workflow listed on the left sidebar
4. If you don't see it, the file might not be pushed yet

### Step 2: Set Up PyPI Token (One-Time)

**Before creating release, add PyPI token:**

1. Go to: https://github.com/Z-MarkUs/PPTrans/settings/secrets/actions
2. Click **"New repository secret"**
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token (get it from https://pypi.org/manage/account/)
5. Click **"Add secret"**

**Note:** Workflow will still run without this, but won't publish to PyPI.

### Step 3: Create Release (This Triggers Workflow)

**Option A: Automated Script**
```bash
./release.sh
```

**Option B: Manual**
```bash
# 1. Tag
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# 2. Create release on GitHub
# Go to: https://github.com/Z-MarkUs/PPTrans/releases/new
# Select tag: v1.0.0
# Add title and description
# Click "Publish release"
```

### Step 4: Watch Workflow Run

**After creating release:**

1. Go to: https://github.com/Z-MarkUs/PPTrans/actions
2. You'll see "Release" workflow running (yellow dot)
3. Click on it to see progress
4. Wait ~2-3 minutes for completion

**What happens:**
- ✅ Builds Python package
- ✅ Validates package
- ✅ Publishes to PyPI (if token set)
- ✅ Uploads artifacts

## Troubleshooting: "I Don't See Workflows"

### Check 1: Is workflow file pushed?

```bash
# Check if you have unpushed commits
git status

# If workflow file shows as untracked/modified:
git add .github/workflows/release.yml
git commit -m "Add release workflow"
git push origin main
```

### Check 2: Where to look on GitHub

**Correct location:**
- Go to: https://github.com/Z-MarkUs/PPTrans
- Click **"Actions"** tab (NOT "Settings")
- Look for **"Release"** in the left sidebar

**If you don't see Actions tab:**
- Make sure you're logged in
- Make sure you're viewing the correct repository
- Try refreshing the page

### Check 3: Test workflow manually

**You can trigger workflow without creating release:**

1. Go to: https://github.com/Z-MarkUs/PPTrans/actions
2. Click **"Release"** workflow (left sidebar)
3. Click **"Run workflow"** button (top right)
4. Select branch: `main`
5. Click **"Run workflow"**

This will run the workflow immediately (good for testing).

## Visual Flow Diagram

```
┌─────────────────────────────────────────┐
│ 1. Push workflow file to GitHub         │
│    git push origin main                  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. Verify workflow appears in Actions   │
│    https://github.com/.../actions       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. Set up PYPI_API_TOKEN secret        │
│    (One-time setup)                    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 4. Create GitHub release                │
│    ./release.sh OR manual               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 5. Workflow runs automatically          │
│    (Triggered by release creation)       │
│    - Builds package                     │
│    - Publishes to PyPI                  │
│    - Uploads artifacts                  │
└─────────────────────────────────────────┘
```

## Quick Verification Commands

```bash
# 1. Check workflow file exists
ls -la .github/workflows/release.yml

# 2. Check if committed
git log --oneline -- .github/workflows/release.yml

# 3. Check if pushed (compare with remote)
git fetch origin
git log origin/main --oneline -- .github/workflows/release.yml

# 4. Push if needed
git push origin main
```

## Expected Timeline

- **Workflow file push**: ~10 seconds
- **Workflow appears in Actions**: Immediately (refresh page)
- **Create release**: ~1 minute
- **Workflow runs**: ~2-3 minutes
- **Package on PyPI**: Available immediately after workflow completes

## Common Mistakes

❌ **Creating release before workflow is pushed**
- Workflow won't trigger for that release
- Fix: Push workflow, then create a new release

❌ **Looking in wrong place for workflows**
- Looking locally instead of GitHub
- Fix: Go to GitHub → Actions tab

❌ **Not setting PYPI_API_TOKEN**
- Workflow runs but doesn't publish
- Fix: Add token in Settings → Secrets

## Next Steps After First Release

1. ✅ Verify package on PyPI: https://pypi.org/project/ppt-translator/
2. ✅ Test installation: `pip install ppt-translator`
3. ✅ Check GitHub release page for artifacts
4. ✅ Share release with users!

