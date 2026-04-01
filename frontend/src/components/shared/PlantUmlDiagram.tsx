import { useState } from "react";
import plantumlEncoder from "plantuml-encoder";

interface PlantUmlDiagramProps {
  /** Raw PlantUML source (without @startuml/@enduml wrapper — added automatically if missing) */
  source: string;
  /** Alt text for the image */
  alt?: string;
  /** Optional CSS class */
  className?: string;
}

/**
 * Renders a PlantUML diagram as an SVG image via a PlantUML server.
 *
 * Server URL is configurable via VITE_PLANTUML_SERVER env var.
 * Default: https://www.plantuml.com/plantuml
 *
 * For offline use, run a local PlantUML server:
 *   docker run -d -p 8080:8080 plantuml/plantuml-server:jetty
 *   VITE_PLANTUML_SERVER=http://localhost:8080 npm run dev
 */
export function PlantUmlDiagram({ source, alt = "Diagram", className }: PlantUmlDiagramProps) {
  const [error, setError] = useState(false);

  const wrapped = source.trimStart().startsWith("@start")
    ? source
    : `@startuml\n${source}\n@enduml`;
  const encoded = plantumlEncoder.encode(wrapped);
  const serverBase =
    import.meta.env.VITE_PLANTUML_SERVER ?? "https://www.plantuml.com/plantuml";
  const url = `${serverBase}/svg/${encoded}`;

  if (error) {
    return (
      <div className={`flex items-center justify-center bg-gray-950 border border-red-900 rounded px-4 py-8 ${className ?? ""}`}>
        <p className="text-red-400 text-sm">
          Failed to load diagram. Check network or set <code className="text-red-300">VITE_PLANTUML_SERVER</code> for local rendering.
        </p>
      </div>
    );
  }

  return (
    <img
      src={url}
      alt={alt}
      className={className}
      loading="lazy"
      onError={() => setError(true)}
    />
  );
}
