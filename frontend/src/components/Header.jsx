import { useState } from "react";
import { NavLink } from "react-router-dom";

const LINKS = [
  ["/", "Explorer"],
  ["/about", "About"],
  ["/data", "Data sources"],
  ["/model", "Model"],
  ["/limitations", "Limitations"],
];

export default function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <div>
          <h1>Solar Market Reality</h1>
          <p>Off-grid solar market evidence for Rwanda</p>
        </div>
      </div>
      <button className="nav-toggle" aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>
        Menu
      </button>
      <nav id="main-nav" aria-label="Main" className={open ? "open" : ""}>
        {LINKS.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}>{label}</NavLink>
        ))}
      </nav>
    </header>
  );
}
