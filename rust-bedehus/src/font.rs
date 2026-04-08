use std::fs;
use std::sync::OnceLock;

use anyhow::{Result, anyhow};
use plotters::prelude::FontStyle;
use plotters::style::register_font;

static FONT_INIT: OnceLock<()> = OnceLock::new();

pub fn ensure_plotters_font() -> Result<()> {
    if FONT_INIT.get().is_some() {
        return Ok(());
    }

    let candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
    ];

    for candidate in candidates {
        if let Ok(bytes) = fs::read(candidate) {
            let leaked: &'static [u8] = Box::leak(bytes.into_boxed_slice());
            register_font("sans-serif", FontStyle::Normal, leaked)
                .map_err(|_| anyhow!("Kunne ikke registrere font fra {candidate}"))?;
            FONT_INIT.set(()).ok();
            return Ok(());
        }
    }

    Err(anyhow!("Fant ingen brukbar TTF-font for Plotters"))
}
