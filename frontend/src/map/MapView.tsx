import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, LineLayer } from "@deck.gl/layers";
import type { Interconnector, Zone, ZonesGeoJSON } from "../types";

// Free dark basemap, no API key (Carto Dark Matter GL style).
const DARK_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const EUROPE_CENTER: [number, number] = [8, 52];
const EUROPE_BOUNDS: [[number, number], [number, number]] = [
  [-25, 33],
  [42, 72],
];

interface Props {
  zones: Zone[];
  borders: Interconnector[];
  geojson: ZonesGeoJSON | null;
}

export default function MapView({ zones, borders, geojson }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      center: EUROPE_CENTER,
      zoom: 3.6,
      maxBounds: EUROPE_BOUNDS,
      attributionControl: { compact: true },
    });
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );

    const overlay = new MapboxOverlay({
      layers: [],
      getTooltip: ({ object, layer }) => {
        if (!object) return null;
        if (layer?.id === "zones") {
          const p = (object as { properties: { key: string; name: string } })
            .properties;
          return { text: `${p.key} — ${p.name}` };
        }
        if (layer?.id === "borders") {
          const b = object as Interconnector;
          const tags = [
            b.capacity_regime === "FLOW_BASED" ? "flow-based" : "NTC",
            ...(b.gb_decoupled ? ["GB decoupled"] : []),
            ...b.cables.map((c) => c.name),
          ];
          return { text: `${b.from_zone} ↔ ${b.to_zone}\n${tags.join(" · ")}` };
        }
        return null;
      },
    });
    map.addControl(overlay);

    mapRef.current = map;
    overlayRef.current = overlay;

    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, []);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;

    const centroids = new Map(zones.map((z) => [z.key, z.centroid]));
    const linkable = borders.filter(
      (b) => centroids.has(b.from_zone) && centroids.has(b.to_zone),
    );

    overlay.setProps({
      layers: [
        geojson
          ? new GeoJsonLayer({
              id: "zones",
              data: geojson,
              stroked: true,
              filled: true,
              getFillColor: [61, 224, 224, 14],
              getLineColor: [61, 224, 224, 80],
              lineWidthMinPixels: 1,
              pickable: true,
              autoHighlight: true,
              highlightColor: [61, 224, 224, 45],
            })
          : null,
        new LineLayer<Interconnector>({
          id: "borders",
          data: linkable,
          getSourcePosition: (b) => centroids.get(b.from_zone)!,
          getTargetPosition: (b) => centroids.get(b.to_zone)!,
          // amber = NTC borders (incl. DC cables), slate = flow-based plate
          getColor: (b) =>
            b.capacity_regime === "NTC"
              ? [251, 191, 36, 150]
              : [148, 163, 184, 90],
          getWidth: 1.5,
          widthUnits: "pixels",
          pickable: true,
        }),
      ],
    });
  }, [zones, borders, geojson]);

  return <div ref={containerRef} style={{ position: "fixed", inset: 0 }} />;
}
