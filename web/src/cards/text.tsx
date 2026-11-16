// The page's own words as blocks: paragraphs, bulleted and numbered lists, and
// simple pipe tables. The model writes markdown; this reads it safely (React
// text nodes only, never raw HTML) and hands inline links and emphasis to
// renderInline. One paragraph of plain text renders exactly as it always did.
import { type ComponentProps, type ReactNode } from "react";
import { renderInline } from "./inline";
import "./text.css";

export type TextBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] };

const BULLET = /^\s{0,3}[-*•]\s+(.*)$/;
const NUMBERED = /^\s{0,3}\d{1,2}[.)]\s+(.*)$/;
const SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function cells(line: string): string[] {
  let body = line.trim();
  if (body.startsWith("|")) body = body.slice(1);
  if (body.endsWith("|") && !body.endsWith("\\|")) body = body.slice(0, -1);
  return body.split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

const startsTable = (lines: string[], index: number): boolean =>
  lines[index].includes("|") && index + 1 < lines.length && lines[index + 1].includes("-") && SEPARATOR.test(lines[index + 1]);

const startsBlock = (lines: string[], index: number): boolean =>
  BULLET.test(lines[index]) || NUMBERED.test(lines[index]) || startsTable(lines, index);

export function parseText(text: string): TextBlock[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: TextBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }
    if (startsTable(lines, index)) {
      const header = cells(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const bullet = BULLET.exec(lines[index]);
    const numbered = bullet ? null : NUMBERED.exec(lines[index]);
    if (bullet || numbered) {
      const pattern = bullet ? BULLET : NUMBERED;
      const items: string[] = [];
      while (index < lines.length) {
        const match = pattern.exec(lines[index]);
        if (match) {
          items.push(match[1].trim());
        } else if (lines[index].trim() && !startsBlock(lines, index) && items.length > 0) {
          items[items.length - 1] += ` ${lines[index].trim()}`;
        } else {
          break;
        }
        index += 1;
      }
      blocks.push({ kind: "list", ordered: Boolean(numbered), items });
      continue;
    }
    const start = index;
    index += 1;
    while (index < lines.length && lines[index].trim() && !startsBlock(lines, index)) index += 1;
    blocks.push({ kind: "paragraph", text: lines.slice(start, index).join("\n") });
  }
  return blocks;
}

const NUMERIC = /^[~≈+\-−–$€£\s]*\d[\d,.:]*\s*(%|x|×)?$/;

function Table({ header, rows }: { header: string[]; rows: string[][] }) {
  const columns = Math.max(header.length, ...rows.map((row) => row.length));
  const numeric = Array.from({ length: columns }, (_, column) => rows.length > 0 && rows.every((row) => !row[column] || NUMERIC.test(row[column])) && rows.some((row) => NUMERIC.test(row[column] ?? "")));
  return (
    <div className="text-table" role="region" aria-label="Table" tabIndex={0}>
      <table>
        <thead>
          <tr>
            {Array.from({ length: columns }, (_, column) => (
              <th key={column} scope="col" className={numeric[column] ? "num" : undefined}>{renderInline(header[column] ?? "")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }, (_, column) => (
                <td key={column} className={numeric[column] ? "num" : undefined}>{renderInline(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderBlock(block: TextBlock, key: number): ReactNode {
  if (block.kind === "paragraph") return <p key={key}>{renderInline(block.text)}</p>;
  if (block.kind === "table") return <Table key={key} header={block.header} rows={block.rows} />;
  const Tag = block.ordered ? "ol" : "ul";
  return (
    <Tag key={key}>
      {block.items.map((item, index) => <li key={index}>{renderInline(item)}</li>)}
    </Tag>
  );
}

// Blocks for any text. A lone paragraph comes back as its bare inline content
// so the caller's own element wraps it exactly as before.
export function renderText(text: string): ReactNode {
  const blocks = parseText(text);
  if (blocks.length === 0) return renderInline(text);
  if (blocks.length === 1 && blocks[0].kind === "paragraph") return renderInline(blocks[0].text);
  return blocks.map(renderBlock);
}

// The element for a lead: the familiar <p> for one paragraph, a <div> of blocks
// when the model wrote more.
export function RichText({ text, className, ...rest }: { text: string; className?: string } & Omit<ComponentProps<"p">, "children" | "className">) {
  const blocks = parseText(text);
  const single = blocks.length <= 1 && (blocks.length === 0 || blocks[0].kind === "paragraph");
  if (single) return <p className={className} {...rest}>{renderText(text)}</p>;
  return <div className={`${className ? `${className} ` : ""}rich-text`} {...(rest as ComponentProps<"div">)}>{renderText(text)}</div>;
}
