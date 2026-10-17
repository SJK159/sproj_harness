import { forwardRef } from 'react';
import { motion, type HTMLMotionProps } from 'framer-motion';
import { cn } from '../../lib/format';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-accent-ink hover:bg-accent/90 shadow-sm',
  secondary: 'border border-line bg-surface text-ink hover:bg-sunk',
  ghost: 'text-muted hover:bg-sunk hover:text-ink',
  danger: 'border border-red-200 bg-surface text-red-700 hover:bg-red-50 dark:border-red-400/30 dark:text-red-300 dark:hover:bg-red-400/10',
};
const SIZES = { sm: 'h-8 px-2.5 text-[13px]', md: 'h-10 px-3.5 text-sm', icon: 'h-8 w-8' };

export type ButtonProps = HTMLMotionProps<'button'> & { variant?: Variant; size?: keyof typeof SIZES };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', className, type = 'button', ...rest }, ref,
) {
  return (
    <motion.button
      ref={ref}
      type={type}
      whileTap={{ scale: 0.97 }}
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-xl font-medium transition-colors disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant], SIZES[size], className,
      )}
      {...rest}
    />
  );
});
