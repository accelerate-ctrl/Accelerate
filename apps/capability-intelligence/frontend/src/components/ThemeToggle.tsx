import { Moon, Sun } from 'lucide-react';
import { toggleTheme, useTheme } from '@/lib/theme';

/**
 * Theme toggle icon button — sun in light mode, moon in dark mode.
 * Per UI/UX Brief §6.1: 36×36 icon button with required aria-label.
 */
export default function ThemeToggle({ className = '' }: { className?: string }) {
  const theme = useTheme();
  const isDark = theme === 'dark';
  const label = isDark ? 'Switch to light mode' : 'Switch to dark mode';
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      className={
        'inline-flex h-9 w-9 items-center justify-center rounded transition-colors ' +
        'text-zen-dark-teal hover:bg-zen-ice/60 dark:text-zen-light-teal dark:hover:bg-zen-dark-teal/40 ' +
        className
      }
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
