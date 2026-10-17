import { GraduationCap } from 'lucide-react';

export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size, borderRadius: size * 0.3 }}
      className="grid shrink-0 place-items-center bg-accent text-accent-ink"
    >
      <GraduationCap style={{ width: size * 0.58, height: size * 0.58 }} strokeWidth={1.9} />
    </span>
  );
}
