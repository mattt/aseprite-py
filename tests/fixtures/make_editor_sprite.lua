-- Writes a small sprite for tests/fixtures/editor.aseprite.
-- Run: aseprite -b --script-param output=editor.aseprite --script make_editor_sprite.lua

local output = app.params["output"]
if output == nil or output == "" then
  error("pass --script-param output=<path>")
end

local spr = Sprite(8, 8, ColorMode.RGB)
spr.layers[1].name = "base"
local base = spr.cels[1]
base.image:drawPixel(1, 1, Color({ r = 255, g = 0, b = 0, a = 255 }))
base.image:drawPixel(2, 1, Color({ r = 0, g = 255, b = 0, a = 255 }))

local overlay = spr:newLayer()
overlay.name = "overlay"
local cel = spr:newCel(overlay, 1)
cel.image:drawPixel(1, 2, Color({ r = 0, g = 0, b = 255, a = 255 }))

local tag = spr:newTag(1, 1)
tag.name = "idle"

spr:saveAs(output)
