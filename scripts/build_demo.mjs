/**
 * Author the synthetic public demo and its visual-QA evidence with Codex's bundled
 * @oai/artifact-tool runtime. The raw PPTX is normalized separately by
 * sanitize_demo_metadata.py before it is committed.
 */
import fs from "node:fs/promises";
import path from "node:path";

import { Presentation, PresentationFile } from "@oai/artifact-tool";

const outputPath = process.argv[2];
const qaDir = process.argv[3];

if (!outputPath || !qaDir) {
  throw new Error("usage: build_demo.mjs OUTPUT_PPTX QA_DIR");
}

const INK = "#000000";
const MUTED = "#5F6672";
const PANEL = "#EDEDED";
const RULE = "#B8BCC4";
const ACCENT = "#3D8DFF";
const ACCENT_LIGHT = "#D0EDFA";
const FONT = "Arial";

function addText(slide, name, position, value, style) {
  const box = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  box.text = value;
  box.text.style = {
    typeface: FONT,
    color: INK,
    autoFit: "none",
    wrap: "square",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
    ...style,
  };
  return box;
}

function addFooter(slide, number) {
  addText(
    slide,
    `footer-${number}`,
    { left: 1160, top: 665, width: 78, height: 22 },
    String(number).padStart(2, "0"),
    { fontSize: 16, color: MUTED, alignment: "right" },
  );
}

function addCover(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = "#FFFFFF";
  addText(
    slide,
    "eyebrow",
    { left: 56, top: 42, width: 500, height: 36 },
    "PPTRANS | EDITABLE PPTX LOCALIZATION",
    { fontSize: 22, bold: true, color: ACCENT },
  );
  const title = addText(
    slide,
    "cover-title",
    { left: 56, top: 178, width: 1080, height: 244 },
    "",
    { fontSize: 72, lineSpacing: 0.92, verticalAlignment: "bottom" },
  );
  title.text.set([
    [
      { run: "Translate PowerPoint.\n", textStyle: { bold: true, color: INK } },
      { run: "Preserve the PowerPoint.", textStyle: { bold: true, color: ACCENT } },
    ],
  ]);
  addText(
    slide,
    "cover-subtitle",
    { left: 56, top: 488, width: 810, height: 104 },
    "PPTrans patches only planned text nodes, verifies the package, and never overwrites the source deck.",
    { fontSize: 28, color: MUTED, lineSpacing: 1.05 },
  );
  const link = addText(
    slide,
    "repository-link",
    { left: 56, top: 628, width: 520, height: 32 },
    "github.com/Z-MarkUs/PPTrans",
    { fontSize: 20, color: ACCENT },
  );
  link.text.get("github.com/Z-MarkUs/PPTrans").link = {
    uri: "https://github.com/Z-MarkUs/PPTrans",
    isExternal: true,
  };
  addFooter(slide, 1);
}

function addTransaction(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = "#FFFFFF";
  addText(
    slide,
    "transaction-title",
    { left: 56, top: 42, width: 1168, height: 82 },
    "A translation becomes a verified transaction",
    { fontSize: 50, bold: true },
  );
  addText(
    slide,
    "transaction-subtitle",
    { left: 56, top: 132, width: 980, height: 54 },
    "Three boundaries keep presentation content, formatting, and failures explicit.",
    { fontSize: 24, color: MUTED },
  );

  const columns = [
    {
      number: "01",
      heading: "Inspect",
      body: "Stable shape IDs and source hashes locate every editable text span.",
    },
    {
      number: "02",
      heading: "Translate",
      body: "Providers return strict JSON with exact unit and span IDs in order.",
    },
    {
      number: "03",
      heading: "Verify",
      body: "Only planned text nodes may change before the output is published atomically.",
    },
  ];
  columns.forEach((column, index) => {
    const left = 56 + index * 392;
    addText(
      slide,
      `step-number-${column.number}`,
      { left, top: 232, width: 330, height: 126 },
      column.number,
      { fontSize: 96, bold: true, color: index === 1 ? ACCENT : ACCENT_LIGHT },
    );
    const body = addText(
      slide,
      `step-body-${column.number}`,
      { left, top: 405, width: 336, height: 172 },
      "",
      { fontSize: 25, lineSpacing: 1.05 },
    );
    body.text.set([
      [
        { run: column.heading, textStyle: { bold: true, fontSize: "28px" } },
        { run: "\n" },
        { run: column.body, textStyle: { color: MUTED, fontSize: "24px" } },
      ],
    ]);
  });
  addFooter(slide, 2);
}

function addCoverage(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = "#FFFFFF";
  addText(
    slide,
    "coverage-title",
    { left: 56, top: 40, width: 1168, height: 80 },
    "Structure stays fixed while text changes",
    { fontSize: 50, bold: true },
  );
  addText(
    slide,
    "coverage-subtitle",
    { left: 56, top: 126, width: 1120, height: 64 },
    "This synthetic fixture exercises rich text, tables, Unicode, numbers, and literal values.",
    { fontSize: 24, color: MUTED },
  );

  const values = [
    ["Fixture", "Source text", "Expected target", "Preservation guard"],
    ["Emphasis", "Bold run", "粗体文本", "Run count unchanged"],
    ["Table cell", "Gross margin", "毛利率", "Cell address stable"],
    ["Unicode", "Hello 🌏", "你好 🌏", "UTF-8 round-trip"],
    ["Number", "Q3: 42.6%", "Q3：42.6%", "Numeric token retained"],
    ["Literal", "PPTrans v2", "PPTrans v2", "Exact text retained"],
  ];
  const table = slide.tables.add({
    rows: values.length,
    columns: values[0].length,
    left: 56,
    top: 222,
    width: 1168,
    height: 390,
    columnWidths: [205, 290, 275, 398],
    values,
  });
  table.styleOptions = { headerRow: true, bandedRows: false };
  table.borders.assign({ style: "solid", fill: RULE, width: 1 });
  table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: 4 }).assign({
    fill: INK,
    textStyle: { color: "#FFFFFF", bold: true, fontSize: 22, typeface: FONT },
    margins: { top: 8, right: 10, bottom: 8, left: 10 },
    anchor: "middle",
  });
  table.cells.block({ row: 1, column: 0, rowCount: 5, columnCount: 4 }).assign({
    fill: "#FFFFFF",
    textStyle: { color: INK, fontSize: 22, typeface: FONT },
    margins: { top: 8, right: 10, bottom: 8, left: 10 },
    anchor: "middle",
  });
  for (let row = 2; row < values.length; row += 2) {
    table.cells.block({ row, column: 0, rowCount: 1, columnCount: 4 }).fill = PANEL;
  }
  addFooter(slide, 3);
}

async function writeBlob(target, blob) {
  await fs.writeFile(target, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.mkdir(qaDir, { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  addCover(presentation);
  addTransaction(presentation);
  addCoverage(presentation);

  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(
      path.join(qaDir, `${stem}.png`),
      await presentation.export({ slide, format: "png", scale: 1.5 }),
    );
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(qaDir, `${stem}.layout.json`), await layout.text());
  }
  await writeBlob(
    path.join(qaDir, "demo-preview.webp"),
    await presentation.export({
      slide: presentation.slides.items[0],
      format: "webp",
      scale: 1,
    }),
  );
  const snapshot = await presentation.inspect({
    kind: "slide,textbox,shape,table",
    maxChars: 20_000,
  });
  await fs.writeFile(path.join(qaDir, "inspect.ndjson"), snapshot.ndjson);
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPath);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
