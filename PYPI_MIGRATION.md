# PyPI Package Name Migration

## Situation

- **Old package name**: `ppt-translator` (already on PyPI)
- **New package name**: `pptrans` (matches project name)

## What Happens

When you publish `pptrans`, it will be a **completely new package** on PyPI. The old `ppt-translator` package will remain unchanged.

## What You Should Do

### Option 1: Just Publish the New Package (Recommended)

1. **Rerun the workflow** - It will publish `pptrans` as a new package
2. **The old `ppt-translator` package stays** - You can't delete packages from PyPI
3. **Optionally deprecate the old package** - See below

### Option 2: Deprecate Old Package (Optional)

If you want to discourage use of the old package:

1. Go to: https://pypi.org/manage/project/ppt-translator/
2. Go to "Release management"
3. Upload a new release (e.g., 1.0.1) with a deprecation notice
4. Or add a note in the project description

## Steps to Publish New Package

1. **Make sure all changes are pushed:**
   ```bash
   git push origin main
   ```

2. **Create a new release** (or manually trigger workflow):
   - Go to: https://github.com/Z-MarkUs/PPTrans/actions
   - Click "Publish to PyPI" workflow
   - Click "Run workflow"
   - Or create a new GitHub release

3. **Verify publication:**
   - Check: https://pypi.org/project/pptrans/
   - Should show version 1.0.0

## Important Notes

- ✅ **You can have both packages** - `ppt-translator` and `pptrans` can coexist
- ✅ **New users install**: `pip install pptrans`
- ⚠️ **Old users still have**: `pip install ppt-translator` (if they already installed it)
- 📝 **Consider**: Adding a note in `ppt-translator` README pointing to `pptrans`

## Deprecation Notice Template

If you want to deprecate `ppt-translator`, you could upload a new release with this in the description:

```
⚠️ DEPRECATED: This package has been renamed to `pptrans`.

Please install the new package:
pip install pptrans

The new package name matches the project name and provides better consistency.
```

## Summary

**Just rerun the workflow** - It will publish `pptrans` as a new package. You don't need to delete anything. The old package can stay (or you can deprecate it later if you want).

