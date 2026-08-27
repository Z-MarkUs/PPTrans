/**
 * Render reproducible source/target showcase evidence with Codex's bundled
 * @oai/artifact-tool runtime. This is visual review evidence, not a PowerPoint-
 * equivalent renderer or a PPTrans runtime dependency.
 */
import fs from "node:fs/promises";
import path from "node:path";

import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const [sourcePath, targetPath, assetsDir, qaDir] = process.argv.slice(2);

if (!sourcePath || !targetPath || !assetsDir || !qaDir) {
  throw new Error(
    "usage: render_demo_comparison.mjs SOURCE_PPTX TARGET_PPTX ASSETS_DIR QA_DIR",
  );
}

async function assertAbsent(target) {
  try {
    await fs.lstat(target);
  } catch (error) {
    if (error?.code === "ENOENT") {
      return;
    }
    throw error;
  }
  throw new Error(`refusing to overwrite existing evidence: ${target}`);
}

async function writeBlob(target, blob) {
  await fs.writeFile(target, new Uint8Array(await blob.arrayBuffer()), { flag: "wx" });
}

function assetPath(label, slideNumber) {
  return path.join(
    assetsDir,
    `pptrans-demo-${label}-slide-${String(slideNumber).padStart(2, "0")}.webp`,
  );
}

async function renderDeck(label, deckPath) {
  const presentation = await PresentationFile.importPptx(await FileBlob.load(deckPath));
  if (presentation.slides.items.length !== 3) {
    throw new Error(`${label} demo must contain exactly three slides`);
  }
  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `${label}-slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(
      assetPath(label, index + 1),
      await presentation.export({ slide, format: "webp", scale: 0.75 }),
    );
    await writeBlob(
      path.join(qaDir, `${stem}.png`),
      await presentation.export({ slide, format: "png", scale: 1.5 }),
    );
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(qaDir, `${stem}.layout.json`), await layout.text(), {
      flag: "wx",
    });
  }
  const inspection = await presentation.inspect({
    kind: "slide,textbox,shape,table",
    maxChars: 40_000,
  });
  await fs.writeFile(path.join(qaDir, `${label}.inspect.ndjson`), inspection.ndjson, {
    flag: "wx",
  });
}

async function main() {
  if (path.resolve(sourcePath) === path.resolve(targetPath)) {
    throw new Error("source and target decks must be distinct");
  }
  await fs.mkdir(assetsDir, { recursive: true });
  await fs.mkdir(qaDir, { recursive: false });
  const evidencePaths = ["source", "zh-CN"].flatMap((label) =>
    [1, 2, 3].map((slideNumber) => assetPath(label, slideNumber)),
  );
  await Promise.all(evidencePaths.map(assertAbsent));
  await renderDeck("source", sourcePath);
  await renderDeck("zh-CN", targetPath);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
