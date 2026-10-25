import { Navigate, Route, Routes } from "react-router-dom";

import { GameShell } from "./components/GameShell";
import { SoundLayer } from "./components/SoundLayer";
import { Blitz } from "./screens/Blitz";
import { Home } from "./screens/Home";
import { Join } from "./screens/Join";
import { Leaderboard } from "./screens/Leaderboard";
import { Lobby } from "./screens/Lobby";
import { Round } from "./screens/Round";
import { Winner } from "./screens/Winner";

export default function App() {
  return (
    <>
    <SoundLayer />
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/join" element={<Join />} />
      <Route path="/lobby/:code" element={<Lobby />} />
      {/* One camera and Presage session for the whole game; see GameShell. Both
          playing screens live under it: `phasePath` picks between them by mode. */}
      <Route element={<GameShell />}>
        <Route path="/play/:code" element={<Round />} />
        <Route path="/play/:code/blitz" element={<Blitz />} />
      </Route>
      <Route path="/play/:code/results" element={<Leaderboard />} />
      <Route path="/play/:code/winner" element={<Winner />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}
