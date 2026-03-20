interface PlaceholderPanelProps {
  title: string;
  subtitle: string;
}

export function PlaceholderPanel({ title, subtitle }: PlaceholderPanelProps) {
  return (
    <div className="rounded border border-gray-800 bg-gray-950 px-4 py-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
        {title}
      </h3>
      <p className="mt-1 text-xs text-gray-600">{subtitle}</p>
    </div>
  );
}
