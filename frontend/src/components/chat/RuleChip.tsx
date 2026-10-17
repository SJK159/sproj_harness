import { BookOpen } from 'lucide-react';
import { RULES, ruleKey } from '../../lib/rules';
import { Tooltip } from '../ui/Tooltip';

/** Inline chip for a rule label like "FE-4 (placeholder v0.1)". Hover/focus shows the rule text. */
export function RuleChip({ label }: { label: string }) {
  const key = ruleKey(label);
  const rule = key ? RULES[key] : undefined;
  const placeholder = /placeholder/i.test(label);
  return (
    <Tooltip
      content={
        <span className="block">
          <span className="block font-semibold">{key}: {rule?.title ?? 'Unknown rule'}</span>
          {rule && <span className="mt-0.5 block opacity-90">{rule.text}</span>}
          <span className="mt-1 block opacity-70">Placeholder rule (v0.1) written by the team, not official LUMS policy.</span>
        </span>
      }
    >
      <span
        tabIndex={0}
        className="mx-0.5 inline-flex translate-y-[-1px] cursor-help items-center gap-1 whitespace-nowrap rounded-md border border-accent/25 bg-accent-soft px-1.5 py-[1px] align-middle text-[12px] font-medium text-accent"
      >
        <BookOpen aria-hidden className="h-3 w-3" />
        {key ?? label}
        {placeholder && <span className="font-normal opacity-75">placeholder</span>}
      </span>
    </Tooltip>
  );
}
