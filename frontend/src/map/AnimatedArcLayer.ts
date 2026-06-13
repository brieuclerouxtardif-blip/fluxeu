// ArcLayer subclass that animates a travelling "comet" along each arc, from
// source -> target. This is the hero flow visual (PLAN §4.1 / §11): the moving
// pulse encodes flow DIRECTION; arc width encodes |MW|.
//
// deck.gl 9 has no built-in arc animation, so we inject a fragment hook that
// modulates alpha by a time-advancing function of the along-arc coordinate
// (geometry.uv.x, 0 at source -> 1 at target). Time is self-driven from the
// wall clock and we request a redraw every frame, so no React re-render is
// needed to animate. The effect is skipped during the picking pass so hover
// detection stays solid.

import { ArcLayer } from "@deck.gl/layers";
import type { ArcLayerProps } from "@deck.gl/layers";
import type { DefaultProps } from "@deck.gl/core";

type AnimatedArcExtraProps = {
  /** Pulses travelling per arc length unit. */
  dashes?: number;
  /** Travel speed (cycles per second). */
  speed?: number;
  /** Resting alpha of the arc between pulses (0..1). */
  baseAlpha?: number;
};

export type AnimatedArcLayerProps<DataT = unknown> = ArcLayerProps<DataT> &
  AnimatedArcExtraProps;

// luma.gl v9 shader module: a std140 uniform block fed via shaderInputs.setProps.
const animModule = {
  name: "anim",
  vs: "",
  fs: `\
layout(std140) uniform animUniforms {
  float uTime;
  float uSpeed;
  float uDashes;
  float uBaseAlpha;
} anim;`,
  uniformTypes: {
    uTime: "f32",
    uSpeed: "f32",
    uDashes: "f32",
    uBaseAlpha: "f32",
  },
} as const;

export default class AnimatedArcLayer<DataT = unknown> extends ArcLayer<
  DataT,
  Required<AnimatedArcExtraProps>
> {
  static layerName = "AnimatedArcLayer";
  static defaultProps: DefaultProps<AnimatedArcLayerProps> = {
    ...ArcLayer.defaultProps,
    dashes: { type: "number", value: 2 },
    speed: { type: "number", value: 0.5 },
    baseAlpha: { type: "number", value: 0.22 },
  };

  initializeState() {
    super.initializeState();
    (this.state as { startTime?: number }).startTime = Date.now();
  }

  getShaders() {
    const shaders = super.getShaders();
    shaders.modules = [...shaders.modules, animModule];
    shaders.inject = {
      "fs:DECKGL_FILTER_COLOR": `
        if (picking.isActive < 0.5) {
          float u = geometry.uv.x;
          float v = fract(u * anim.uDashes - anim.uTime * anim.uSpeed);
          float comet = pow(1.0 - v, 3.0);
          color.a *= anim.uBaseAlpha + (1.0 - anim.uBaseAlpha) * comet;
        }
      `,
    };
    return shaders;
  }

  draw(opts: { uniforms: unknown }) {
    const start = (this.state as { startTime?: number }).startTime ?? Date.now();
    const elapsed = (Date.now() - start) / 1000;
    const model = this.state.model;
    if (model) {
      model.shaderInputs.setProps({
        anim: {
          uTime: elapsed,
          uSpeed: this.props.speed,
          uDashes: this.props.dashes,
          uBaseAlpha: this.props.baseAlpha,
        },
      });
    }
    super.draw(opts);
    // Keep the animation loop alive only while there are arcs to animate;
    // otherwise the layer renders once and the page can go idle.
    const data = this.props.data as ArrayLike<unknown> | undefined;
    if (data && data.length > 0) this.setNeedsRedraw();
  }
}
