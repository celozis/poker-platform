/** The Siberian Poker League mark, shown next to every club's own branding. */
export default function LeagueBrand({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0" aria-hidden="true">
        <circle cx="16" cy="16" r="15" fill="#0F172A" />
        <path
          d="M16 6c-3 4-8 6.5-8 11a4 4 0 0 0 7 2.6L14 25h4l-1-5.4A4 4 0 0 0 24 17c0-4.5-5-7-8-11z"
          fill="#E2E8F0"
        />
      </svg>
      <span className="text-sm font-semibold tracking-wide uppercase">
        Сибирская лига покера
      </span>
    </div>
  );
}
