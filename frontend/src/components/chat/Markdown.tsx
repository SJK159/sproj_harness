import { Fragment, type ReactNode } from 'react';
import { RULE_PATTERN } from '../../lib/rules';
import { cn } from '../../lib/format';
import { RuleChip } from './RuleChip';

// Small, dependency-free Markdown renderer: headings, lists, tables, bold, italic, code, links,
// blockquotes, plus rule chips and case ids.

const INLINE = new RegExp(
  [
    '(`[^`]+`)',
    '(\\*\\*[^*]+\\*\\*)',
    '(\\[[^\\]]+\\]\\([^)\\s]+\\))',
    '(FE-[0-9a-f]{8}\\b)',
    `(${RULE_PATTERN})`,
    '(\\*[^*\\s][^*]*\\*|\\b_[^_\\s][^_]*_\\b)',
  ].join('|'),
  'g',
);

export function renderInline(text: string, keyPrefix = 'i'): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  INLINE.lastIndex = 0;
  for (let m = INLINE.exec(text); m; m = INLINE.exec(text)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${keyPrefix}-${i++}`;
    const [tok] = m;
    if (m[1]) out.push(<code key={k} className="rounded bg-sunk px-1 py-[1px] font-mono text-[0.88em]">{tok.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={k} className="font-semibold text-ink">{renderInline(tok.slice(2, -2), k)}</strong>);
    else if (m[3]) {
      const lm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(tok);
      out.push(<a key={k} href={lm?.[2]} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2 hover:opacity-80">{lm?.[1]}</a>);
    } else if (m[4]) out.push(<span key={k} className="whitespace-nowrap font-mono text-[0.9em] tabular-nums">{tok}</span>);
    else if (m[5]) out.push(<RuleChip key={k} label={tok} />);
    else if (m[6]) out.push(<em key={k}>{renderInline(tok.slice(1, -1), k)}</em>);
    last = m.index + tok.length;
    INLINE.lastIndex = last;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { t: 'h'; level: number; text: string }
  | { t: 'p'; text: string }
  | { t: 'ul' | 'ol'; items: string[] }
  | { t: 'code'; text: string }
  | { t: 'quote'; text: string }
  | { t: 'table'; head: string[]; rows: string[][] };

const cells = (line: string) => line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.startsWith('```')) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++]);
      i++;
      blocks.push({ t: 'code', text: buf.join('\n') });
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { blocks.push({ t: 'h', level: h[1].length, text: h[2] }); i++; continue; }
    if (line.trim().startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]));
      blocks.push({ t: 'table', head, rows });
      continue;
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const re = ordered ? /^\s*\d+\.\s+/ : /^\s*[-*]\s+/;
      const items: string[] = [];
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ''));
      blocks.push({ t: ordered ? 'ol' : 'ul', items });
      continue;
    }
    if (line.startsWith('>')) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith('>')) buf.push(lines[i++].replace(/^>\s?/, ''));
      blocks.push({ t: 'quote', text: buf.join(' ') });
      continue;
    }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*[-*]\s+|\s*\d+\.\s+|>|\s*\|)/.test(lines[i])) buf.push(lines[i++]);
    if (!buf.length) buf.push(lines[i++]);
    blocks.push({ t: 'p', text: buf.join(' ') });
  }
  return blocks;
}

export function Markdown({ text, streaming = false, className }: { text: string; streaming?: boolean; className?: string }) {
  const blocks = parse(text);
  return (
    <div className={cn('space-y-3 text-[15px] leading-[1.65] text-ink [text-wrap:pretty]', className)}>
      {blocks.map((b, bi) => {
        const isLast = bi === blocks.length - 1;
        const caret = streaming && isLast ? 'caret' : undefined;
        const k = `b${bi}`;
        switch (b.t) {
          case 'h': {
            const cls = b.level <= 2 ? 'text-[17px] font-semibold text-navy' : 'text-[15px] font-semibold text-navy';
            return <div key={k} role="heading" aria-level={b.level + 1} className={cn(cls, caret)}>{renderInline(b.text, k)}</div>;
          }
          case 'p': return <p key={k} className={caret}>{renderInline(b.text, k)}</p>;
          case 'quote': return <blockquote key={k} className={cn('border-l-2 border-line pl-3 text-muted', caret)}>{renderInline(b.text, k)}</blockquote>;
          case 'code': return <pre key={k} className="scroll-thin overflow-x-auto rounded-xl bg-sunk p-3 font-mono text-[13px] leading-relaxed">{b.text}</pre>;
          case 'ul':
          case 'ol': {
            const L = b.t === 'ul' ? 'ul' : 'ol';
            return (
              <L key={k} className={cn('space-y-1 pl-5', b.t === 'ul' ? 'list-disc marker:text-faint' : 'list-decimal marker:text-faint')}>
                {b.items.map((it, ii) => <li key={ii} className={isLast && ii === b.items.length - 1 ? caret : undefined}>{renderInline(it, `${k}-${ii}`)}</li>)}
              </L>
            );
          }
          case 'table':
            return (
              <div key={k} className="scroll-thin overflow-x-auto rounded-xl border border-line">
                <table className="w-full text-left text-[13.5px]">
                  <thead className="bg-sunk text-muted"><tr>{b.head.map((h, hi) => <th key={hi} className="px-3 py-2 font-medium">{renderInline(h, `${k}h${hi}`)}</th>)}</tr></thead>
                  <tbody>{b.rows.map((r, ri) => <tr key={ri} className="border-t border-line">{r.map((c, ci) => <td key={ci} className="px-3 py-2 align-top">{renderInline(c, `${k}r${ri}c${ci}`)}</td>)}</tr>)}</tbody>
                </table>
              </div>
            );
          default: return <Fragment key={k} />;
        }
      })}
      {streaming && blocks.length === 0 && <p className="caret" />}
    </div>
  );
}
