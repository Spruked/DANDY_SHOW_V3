import React from "react";
import "./WebsiteORB.css";

type OrbState = "idle" | "listening" | "speaking";

export const Orb: React.FC<{
  size?: number;
  state?: OrbState;
  onClick?: () => void;
  skinSrc?: string;
}> = ({
  size = 200,
  state = "idle",
  onClick,
  skinSrc = "/orb-skins/tuxorb.png",
}) => {
  return (
    <button
      type="button"
      className={`ow-v2-orb-body ${state} has-image-skin`}
      style={{ width: size, height: size }}
      aria-label="Orb Weaver intelligence orb"
      onClick={onClick}
    >
      <div className="ow-v2-orb-halo" />
      <img className="ow-v2-orb-skin-image" src={skinSrc} alt="" draggable={false} />
      <div className="ow-v2-orb-eye-pulse" />
      <div className="ow-v2-orb-specular" />
    </button>
  );
};

export default Orb;
