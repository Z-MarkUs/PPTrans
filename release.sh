#!/bin/bash
# Automated GitHub release script for PPT Translator

set -e

# Configuration
VERSION="1.0.0"
TAG="v${VERSION}"
REPO="Z-MarkUs/PPTrans"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Creating release ${TAG}...${NC}"

# Check if we're on the main branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ] && [ "$CURRENT_BRANCH" != "master" ]; then
    echo -e "${YELLOW}⚠️  Warning: Not on main/master branch (current: ${CURRENT_BRANCH})${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}❌ Error: You have uncommitted changes${NC}"
    echo "Please commit or stash them before creating a release"
    exit 1
fi

# Build packages
echo -e "${GREEN}📦 Building Python package...${NC}"
if ! python3 -m build; then
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

# Check if tag already exists
if git rev-parse "${TAG}" >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Tag ${TAG} already exists${NC}"
    read -p "Delete and recreate? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git tag -d "${TAG}"
        git push origin ":refs/tags/${TAG}" 2>/dev/null || true
    else
        echo "Aborting..."
        exit 1
    fi
fi

# Create tag
echo -e "${GREEN}🏷️  Creating tag ${TAG}...${NC}"
git tag -a "${TAG}" -m "Release version ${VERSION}"
git push origin "${TAG}"

# Create release notes file if it doesn't exist
if [ ! -f "RELEASE_NOTES.md" ]; then
    cat > RELEASE_NOTES.md <<EOF
# PPT Translator ${TAG}

## 🎉 Release ${VERSION}

### ✨ Features

- Multi-provider LLM support (DeepSeek, OpenAI, Anthropic, Grok)
- Vision-based quality review with GPT-5.1
- Layout-aware translation with auto font adjustment
- Translation memory for consistency
- Interactive review mode
- User-defined glossary
- Batch processing

### 📦 Installation

\`\`\`bash
pip install ppt-translator
\`\`\`

### 🚀 Quick Start

\`\`\`bash
ppt-translator presentation.pptx --provider openai --source-lang zh --target-lang en
\`\`\`

See [README.md](README.md) for full documentation.
EOF
fi

# Create release with GitHub CLI if available
if command -v gh &> /dev/null; then
    echo -e "${GREEN}📤 Creating GitHub release...${NC}"
    
    # Collect all dist files
    DIST_FILES=$(find dist -type f \( -name "*.whl" -o -name "*.tar.gz" -o -name "*.app" -o -name "*.exe" -o -name "pptrans" \) 2>/dev/null || true)
    
    if [ -z "$DIST_FILES" ]; then
        echo -e "${YELLOW}⚠️  No files found in dist/ directory${NC}"
        echo "Creating release without assets..."
        gh release create "${TAG}" \
            --title "PPT Translator ${TAG}" \
            --notes-file RELEASE_NOTES.md
    else
        echo "Uploading files:"
        echo "$DIST_FILES" | while read -r file; do
            echo "  - $file"
        done
        
        gh release create "${TAG}" \
            --title "PPT Translator ${TAG}" \
            --notes-file RELEASE_NOTES.md \
            $DIST_FILES
    fi
    
    echo -e "${GREEN}✅ Release created successfully!${NC}"
    echo ""
    echo "View release at: https://github.com/${REPO}/releases/tag/${TAG}"
else
    echo -e "${YELLOW}⚠️  GitHub CLI (gh) not found${NC}"
    echo ""
    echo "Please create release manually:"
    echo "1. Go to: https://github.com/${REPO}/releases/new"
    echo "2. Select tag: ${TAG}"
    echo "3. Add title: PPT Translator ${TAG}"
    echo "4. Copy contents of RELEASE_NOTES.md as description"
    echo "5. Upload files from dist/ directory"
    echo "6. Click 'Publish release'"
fi

