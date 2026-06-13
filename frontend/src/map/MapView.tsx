import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, LineLayer } from "@deck.gl/layers";
import AnimatedArcLayer from "./AnimatedArcLayer";
import { priceColor } from "./priceColor";
import type {
  FlowEdge,
  Interconnector,
  LiveSnapshot,
  Zone,
  ZonesGeoJSON,
} from "../types";

// Free dark basemap, no API key (Carto Dark Matter GL style).
const DARK_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const EUROPE_CENTER: [number, number] = [8, 52];
const EUROPE_BOUNDS: [[number, number], [number, number]] = [
  [-25, 33],
  [42, 72],
];

export type FlowMode = "commercial" | "physical";

// Below this |MW| an arc is noise — drop it to keep the hero readable.
const MIN_ARC_MW = 1;

interface Props {
  zones: Zone[];
  borders: Interconnector[];
  geojson: ZonesGeoJSON | null;
  snapshot: LiveSnapshot | null;
  mode: FlowMode;
}

// A directed arc, oriented in the real flow direction for the active mode.
interface ArcDatum {
  edge: FlowEdge;
  value: number; // signed MW for the active mode
  magnitude: number; // |MW|
  source: [number, number];
  target: [number, number];
}

// Tooltip data is read through a ref so the (mount-time) getTooltip closure
// always sees the latest snapshot without recreating the overlay.
interface TooltipData {
  prices: Record<string, number>;
  zoneToCountry: Map<string, string>;
  netPositions: Record<string, number>;
  nodeName: Map<string, string>;
  mode: FlowMode;
}

function buildArcs(snapshot: LiveSnapshot | null, mode: FlowMode): ArcDatum[] {
  if (!snapshot) return [];
  const centroid = new Map(snapshot.nodes.map((n) => [n.code, n.centroid]));
  const arcs: ArcDatum[] = [];
  for (const edge of snapshot.edges) {
    const value = mode === "commercial" ? edge.commercial_mw : edge.physical_mw;
    if (value == null) continue;
    const magnitude = Math.abs(value);
    if (magnitude < MIN_ARC_MW) continue;
    const a = centroid.get(edge.from_zone);
    const b = centroid.get(edge.to_zone);
    if (!a || !b) continue;
    // sign convention: + means from_zone -> to_zone. Draw in that direction.
    const forward = value >= 0;
    arcs.push({
      edge,
      value,
      magnitude,
      source: forward ? a : b,
      target: forward ? b : a,
    });
  }
  return arcs;
}

const fmtMw = (mw: number | null): string =>
  mw == null ? "n/a" : `${Math.round(mw).toLocaleString("en-US")} MW`;

export default function MapView({ zones, borders, geojson, snapshot, mode }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const tipRef = useRef<TooltipData>({
    prices: {},
    zoneToCountry: new Map(),
    netPositions: {},
    nodeName: new Map(),
    mode,
  });

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
        const tip = tipRef.current;
        if (layer?.id === "zones") {
          const p = (object as { properties: { key: string; name: string } })
            .properties;
          const price = tip.prices[p.key];
          const cc = tip.zoneToCountry.get(p.key);
          const net = cc != null ? tip.netPositions[cc] : undefined;
          const lines = [`${p.key} — ${p.name}`];
          lines.push(
            price == null
              ? "price: no day-ahead data"
              : `price: ${price.toFixed(2)} €/MWh${price < 0 ? "  (negative)" : ""}`,
          );
          if (net != null) {
            const verb = net >= 0 ? "net import" : "net export";
            lines.push(`country (${cc}): ${fmtMw(Math.abs(net))} ${verb}`);
          }
          return { text: lines.join("\n") };
        }
        if (layer?.id === "flows") {
          const d = object as ArcDatum;
          const e = d.edge;
          const from = d.value >= 0 ? e.from_zone : e.to_zone;
          const to = d.value >= 0 ? e.to_zone : e.from_zone;
          const fromN = tip.nodeName.get(from) ?? from;
          const toN = tip.nodeName.get(to) ?? to;
          const active = tip.mode === "commercial" ? "commercial" : "physical";
          const lines = [
            `${fromN} → ${toN}`,
            `${active} flow: ${fmtMw(d.magnitude)}`,
            `commercial: ${fmtMw(e.commercial_mw)}`,
            `physical: ${fmtMw(e.physical_mw)}`,
            e.capacity_regime === "FLOW_BASED"
              ? "flow-based border (measured flow)"
              : "NTC border",
          ];
          return { text: lines.join("\n") };
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

    // refresh tooltip lookups
    tipRef.current = {
      prices: snapshot?.prices ?? {},
      zoneToCountry: new Map(
        (snapshot?.nodes ?? []).flatMap((n) => n.zones.map((z) => [z, n.code])),
      ),
      netPositions: snapshot?.net_positions ?? {},
      nodeName: new Map((snapshot?.nodes ?? []).map((n) => [n.code, n.name])),
      mode,
    };

    const centroids = new Map(zones.map((z) => [z.key, z.centroid]));
    const linkable = borders.filter(
      (b) => centroids.has(b.from_zone) && centroids.has(b.to_zone),
    );
    const arcs = buildArcs(snapshot, mode);
    const prices = snapshot?.prices ?? {};

    overlay.setProps({
      layers: [
        // zones colored by current day-ahead price
        geojson
          ? new GeoJsonLayer({
              id: "zones",
              data: geojson,
              stroked: true,
              filled: true,
              getFillColor: (f) => {
                const key = (f.properties as { key: string }).key;
                const p = prices[key];
                if (p == null) return [120, 120, 140, 16];
                const [r, g, b] = priceColor(p);
                return [r, g, b, 170];
              },
              getLineColor: [61, 224, 224, 70],
              lineWidthMinPixels: 0.5,
              pickable: true,
              autoHighlight: true,
              highlightColor: [255, 255, 255, 40],
              updateTriggers: {
                getFillColor: [snapshot?.data_ts ?? "", Object.keys(prices).length],
              },
            })
          : null,
        // faint topology underlay (zone-level borders) — context, not interactive
        new LineLayer<Interconnector>({
          id: "borders",
          data: linkable,
          getSourcePosition: (b) => centroids.get(b.from_zone)!,
          getTargetPosition: (b) => centroids.get(b.to_zone)!,
          getColor: [148, 163, 184, 45],
          getWidth: 1,
          widthUnits: "pixels",
          pickable: false,
        }),
        // animated flow arcs (the hero): width ∝ |MW|, comet = direction
        new AnimatedArcLayer<ArcDatum>({
          id: "flows",
          data: arcs,
          getSourcePosition: (d) => d.source,
          getTargetPosition: (d) => d.target,
          getSourceColor: [45, 212, 191, 255],
          getTargetColor: [186, 230, 253, 255],
          getWidth: (d) => 1.2 + Math.sqrt(d.magnitude) * 0.12,
          getHeight: 0.5,
          widthUnits: "pixels",
          widthMinPixels: 1.2,
          widthMaxPixels: 14,
          dashes: 2,
          speed: 0.5,
          baseAlpha: 0.22,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 200],
          updateTriggers: {
            getSourcePosition: [mode, snapshot?.data_ts ?? ""],
            getTargetPosition: [mode, snapshot?.data_ts ?? ""],
            getWidth: [mode, snapshot?.data_ts ?? ""],
          },
        }),
      ],
    });
  }, [zones, borders, geojson, snapshot, mode]);

  return <div ref={containerRef} style={{ position: "fixed", inset: 0 }} />;
}
