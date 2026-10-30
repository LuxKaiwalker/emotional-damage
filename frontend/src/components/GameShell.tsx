import { createContext, useContext, useMemo } from "react";
import { Outlet, useParams } from "react-router-dom";

import { useSmartSpectra, type Spectra } from "../hooks/useSmartSpectra";
import { loadSessionFor } from "../session";

const SpectraContext = createContext<Spectra | null>(null);

/**
 * Layout around every in-game screen: lobby, round, results, winner.
 *
 * It owns the camera and the Presage session so they outlive the screens. A layout route
 * stays mounted while its children swap, so the session starts once in the lobby and is
 * already reading faces when round 1 begins, instead of restarting -- several seconds of
 * nothing -- at the start of every round.
 */
export function GameShell() {
  const code = (useParams().code ?? "").toUpperCase();
  const session = useMemo(() => loadSessionFor(code), [code]);
  const spectra = useSmartSpectra({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
  });

  return (
    <SpectraContext.Provider value={spectra}>
      <Outlet />
    </SpectraContext.Provider>
  );
}

/** The game's camera and Presage session. Only valid under `GameShell`. */
export function useSpectra(): Spectra {
  const spectra = useContext(SpectraContext);
  if (!spectra) throw new Error("useSpectra must be used inside GameShell");
  return spectra;
}
