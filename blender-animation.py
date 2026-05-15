# ============================================================
# German House — Animation + Colours Script v4
# Run AFTER building_simulation_blender.py
# Animates: room colours, HWT water level, heaters glow,
#           heat pump LED, time-of-day lighting
# ============================================================
import bpy, math, random

# ── CONFIG ───────────────────────────────────────────────────
MODE     = "demo"   # "demo" | "csv"
CSV_PATH = r"C:\Users\anike\i4b\results_mpc\results_sfh_2016_now_0_soc_days30.csv"
FPS      = 24
FRAMES_PER_STEP = 6   # 6 frames per simulation step = smooth animation

# ── COLOUR PALETTE (beautiful, physically meaningful) ────────
# Temperature gradient: cool blue → neutral white → warm orange → hot red
def temp_to_colour(t, t_min=15.0, t_max=28.0):
    """Map temperature to (R,G,B) — blue=cold, green=comfortable, red=hot."""
    t = max(t_min, min(t_max, t))
    f = (t - t_min) / (t_max - t_min)
    if f < 0.33:
        r = 0.10 + f*1.8;  g = 0.30 + f*1.5;  b = 0.85 - f*0.5
    elif f < 0.66:
        ff = (f-0.33)/0.33
        r = 0.69 + ff*0.25; g = 0.80 - ff*0.35; b = 0.35 - ff*0.25
    else:
        ff = (f-0.66)/0.34
        r = 0.94 + ff*0.06; g = 0.45 - ff*0.35; b = 0.10 - ff*0.08
    return (max(0,min(1,r)), max(0,min(1,g)), max(0,min(1,b)))

def soc_to_colour(soc):
    """HWT water colour: dark blue=empty/cold → bright cyan=full/hot."""
    r = 0.05 + soc*0.55
    g = 0.18 + soc*0.55
    b = 0.55 + soc*0.40
    return (r, g, b)

def hp_on_colour():   return (1.00, 0.35, 0.04)  # orange glow
def hp_off_colour():  return (0.18, 0.18, 0.20)  # dark grey

# ── GENERATE DEMO DATA ────────────────────────────────────────
def generate_demo_data(n=240):
    """Realistic 10-day simulation demo: daily temperature cycles."""
    data = []
    t_lr, t_br, t_kt = 20.0, 19.5, 18.5
    soc  = 0.55
    hp   = False
    for i in range(n):
        hour = (i * 1.0) % 24
        # Outdoor temp: colder at night, warmer midday
        t_out = 8 + 5*math.sin((hour-6)/24*2*math.pi)
        # Heat loss proportional to temperature difference
        dt_loss = 0.08 * max(0, t_lr - t_out)
        # Solar gain during day
        solar = max(0, 0.05*math.sin((hour-8)/10*math.pi)) if 8 < hour < 18 else 0
        # HP control: turn on below setpoint, off above
        setpoint = 21.0
        if not hp and (t_lr < setpoint - 0.5 or soc < 0.25):
            hp = True
        if hp and (t_lr > setpoint + 0.3 and soc > 0.80):
            hp = False
        if hp:
            t_lr  = min(22.5, t_lr  + 0.12 - dt_loss*0.4 + solar)
            t_br  = min(22.0, t_br  + 0.09 - dt_loss*0.35 + solar*0.7)
            t_kt  = min(21.5, t_kt  + 0.08 - dt_loss*0.3 + solar*0.6)
            soc   = min(1.0,  soc   + 0.025)
            cop   = 3.2 + 0.4*math.sin(i*0.3)
        else:
            t_lr  = max(17.5, t_lr  - dt_loss*0.5 + solar)
            t_br  = max(17.0, t_br  - dt_loss*0.45 + solar*0.7)
            t_kt  = max(16.5, t_kt  - dt_loss*0.4 + solar*0.6)
            soc   = max(0.0,  soc   - 0.015)
            cop   = 0.0
        data.append({
            'step': i, 'hour': hour,
            'T_lr': t_lr, 'T_br': t_br, 'T_kt': t_kt,
            'SOC': soc, 'HP': hp, 'COP': cop, 'T_out': t_out
        })
    return data

# ── LOAD CSV DATA ─────────────────────────────────────────────
def load_csv_data(path):
    import csv
    data = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            def g(k, default=20.0):
                for key in row:
                    if k.lower() in key.lower():
                        try: return float(row[key])
                        except: pass
                return default
            hp_val = g('action', 0)
            data.append({
                'step': i, 'hour': (i % 96) / 4.0,
                'T_lr': g('T_room', 20), 'T_br': g('T_room', 20),
                'T_kt': g('T_room', 20),
                'SOC': g('SOC', 0.5), 'HP': hp_val > 0.5,
                'COP': g('COP', 0), 'T_out': g('T_out', 10)
            })
    return data

# ── LOAD DATA ─────────────────────────────────────────────────
if MODE == "csv":
    try:
        sim_data = load_csv_data(CSV_PATH)
        print(f"Loaded {len(sim_data)} steps from CSV")
    except Exception as e:
        print(f"CSV load failed: {e}\nFalling back to demo data")
        sim_data = generate_demo_data(240)
else:
    sim_data = generate_demo_data(240)
    print(f"Demo data: {len(sim_data)} steps")

total_frames = len(sim_data) * FRAMES_PER_STEP
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end   = total_frames
bpy.context.scene.render.fps  = FPS

# ── FIND OBJECTS ──────────────────────────────────────────────
def find(name):
    return bpy.data.objects.get(name)

def find_mat(name):
    return bpy.data.materials.get(name)

# Wall material references (interior wall surfaces)
wall_mats = {
    'LR': find_mat("M_Wallpaper"),  # living room interior walls
    'BR': find_mat("M_WallInt"),
    'KT': find_mat("M_WallInt"),
}

# HWT water material
hwt_water_mat = find_mat("M_Water")

# Heater materials — we'll swap emissive per frame
heater_mats = {
    'LR': find_mat("M_HeaterOff"),
    'BR': find_mat("M_HeaterOff"),
    'KT': find_mat("M_HeaterOff"),
}

# LED material
led_mat = find_mat("M_LED_Grn")

# ── HELPER: SET KEYFRAME ──────────────────────────────────────
def key_mat_colour(mat, frame, r, g, b, input_name="Base Color"):
    if mat is None: return
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None: return
    inp = bsdf.inputs.get(input_name)
    if inp is None: return
    inp.default_value = (r, g, b, 1.0)
    inp.keyframe_insert("default_value", frame=frame)

def key_mat_emit(mat, frame, strength, r=1, g=0.35, b=0.04):
    if mat is None: return
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None: return
    ei = bsdf.inputs.get("Emission Strength")
    if ei:
        ei.default_value = strength
        ei.keyframe_insert("default_value", frame=frame)
    ec = bsdf.inputs.get("Emission Color")
    if ec:
        ec.default_value = (r, g, b, 1.0)
        ec.keyframe_insert("default_value", frame=frame)

def key_obj_z_scale(obj, frame, scale_z):
    if obj is None: return
    obj.scale.z = scale_z
    obj.keyframe_insert("scale", frame=frame)

def key_obj_z_loc(obj, frame, z):
    if obj is None: return
    obj.location.z = z
    obj.keyframe_insert("location", frame=frame)

def key_light_energy(light_obj, frame, energy):
    if light_obj is None: return
    light_obj.data.energy = energy
    light_obj.data.keyframe_insert("energy", frame=frame)

def key_light_colour(light_obj, frame, r, g, b):
    if light_obj is None: return
    light_obj.data.color = (r, g, b)
    light_obj.data.keyframe_insert("color", frame=frame)

# ── GET SCENE OBJECTS ─────────────────────────────────────────
hwt_water = find("HWT_Water")
sun_light  = find("Sun")
sky_light  = find("SkyFill")
hwt_glow   = find("HWT_Glow")
led_obj    = find("HP_LED")

room_lights = {
    'LR': find("L_LR"),
    'BR': find("L_BR"),
    'KT': find("L_KT"),
}

# Heater body objects (main back panel — drives glow)
heater_bodies = {
    'LR': find("H_LivingRoom_Bk"),
    'BR': find("H_Bedroom_Bk"),
    'KT': find("H_Kitchen_Bk"),
}

# ── ANIMATE EACH STEP ─────────────────────────────────────────
print("Inserting keyframes...")
for d in sim_data:
    frame = d['step'] * FRAMES_PER_STEP + 1
    soc   = d['SOC']
    hp    = d['HP']
    hour  = d['hour']

    # ── Room wall colours ──────────────────────────────────────
    cr = temp_to_colour(d['T_lr'])
    cg = temp_to_colour(d['T_br'])
    ck = temp_to_colour(d['T_kt'])

    # Each room uses a separate material; modulate Base Color
    # Living room — wallpaper
    m_lr = find_mat("M_Wallpaper")
    if m_lr:
        # Tint the wallpaper with temperature (subtle, ±15%)
        base = (0.93, 0.90, 0.86)
        tinted = (
            base[0]*0.85 + cr[0]*0.15,
            base[1]*0.85 + cr[1]*0.15,
            base[2]*0.85 + cr[2]*0.15,
        )
        key_mat_colour(m_lr, frame, *tinted)

    # Interior walls (bedroom/kitchen share M_WallInt)
    m_wi = find_mat("M_WallInt")
    avg_t = (d['T_br'] + d['T_kt']) / 2
    cw = temp_to_colour(avg_t)
    if m_wi:
        base = (0.96, 0.94, 0.90)
        tinted = (base[0]*0.85+cw[0]*0.15, base[1]*0.85+cw[1]*0.15, base[2]*0.85+cw[2]*0.15)
        key_mat_colour(m_wi, frame, *tinted)

    # ── HWT Water level ────────────────────────────────────────
    # Water object scale.z = soc (0=empty, 1=full)
    water_scale = max(0.05, soc)
    if hwt_water:
        hwt_water.scale.z = water_scale
        hwt_water.keyframe_insert("scale", frame=frame)
        # Shift Z so bottom stays fixed
        hwt_water.location.z = -1.5 - (1.0 - soc) * 0.85
        hwt_water.keyframe_insert("location", frame=frame)
    # Water colour
    wc = soc_to_colour(soc)
    key_mat_colour(find_mat("M_Water"), frame, *wc)

    # ── Heater glow ────────────────────────────────────────────
    glow_str = 4.5 if hp else 0.0
    glow_col = hp_on_colour() if hp else hp_off_colour()
    for room_key in ('LR', 'BR', 'KT'):
        # Heater back panel material
        hbody = heater_bodies.get(room_key)
        if hbody and hbody.data.materials:
            hmat = hbody.data.materials[0]
            if hmat:
                key_mat_colour(hmat, frame, *glow_col)
                key_mat_emit(hmat, frame, glow_str, *glow_col)

    # ── Room lights — brighter when HP running ─────────────────
    interior_brightness = 80 + (hp * 40)
    for lobj in room_lights.values():
        key_light_energy(lobj, frame, interior_brightness)

    # ── HP LED: green=ON, red=OFF ───────────────────────────────
    if led_obj and led_obj.data.materials:
        led_m = led_obj.data.materials[0]
        if led_m:
            led_col = (0.05,0.95,0.15) if hp else (0.95,0.10,0.06)
            key_mat_colour(led_m, frame, *led_col)
            key_mat_emit(led_m, frame, 4.5, *led_col)

    # ── HWT glow light intensity ───────────────────────────────
    hwt_energy = 30 + soc * 120
    key_light_energy(hwt_glow, frame, hwt_energy)
    # Colour: cold=blue, hot=orange
    hw_r = 0.3 + soc*0.7; hw_g = 0.4 + soc*0.2; hw_b = 0.9 - soc*0.8
    key_light_colour(hwt_glow, frame, hw_r, hw_g, hw_b)

    # ── Sun light: day/night cycle ─────────────────────────────
    is_day = 6 < hour < 20
    sun_energy = max(0.0, 4.0 * math.sin((hour-6)/14*math.pi)) if is_day else 0.0
    sun_r = 1.0; sun_g = 0.85 + 0.11*(sun_energy/4.0); sun_b = 0.70 + 0.18*(sun_energy/4.0)
    key_light_energy(sun_light,  frame, sun_energy)
    key_light_colour(sun_light,  frame, sun_r, sun_g, sun_b)
    # Sky fill: dim at night
    sky_energy = 60 + sun_energy * 48
    key_light_energy(sky_light, frame, sky_energy)
    if not is_day:
        key_light_colour(sky_light, frame, 0.10, 0.12, 0.30)  # deep blue night
    else:
        key_light_colour(sky_light, frame, 0.80, 0.90, 1.00)  # sky blue day

    # Interior lights ON at night
    night_boost = 180 if not is_day else 100
    for lobj in room_lights.values():
        key_light_energy(lobj, frame, night_boost if not is_day else interior_brightness)

    if d['step'] % 30 == 0:
        print(f"  Step {d['step']:3d}/{len(sim_data)} | "
              f"T={d['T_lr']:.1f}°C | SOC={soc:.2f} | "
              f"HP={'ON ' if hp else 'OFF'} | {hour:.0f}:00")

# ── SET INTERPOLATION TO LINEAR ──────────────────────────────
def set_linear(anim_owner):
    ad = getattr(anim_owner, 'animation_data', None)
    act = getattr(ad, 'action', None) if ad else None
    fcurves = getattr(act, 'fcurves', None)
    if not fcurves:
        return
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'

for mat in bpy.data.materials:
    nt = getattr(mat, 'node_tree', None)
    if nt:
        set_linear(nt)

for obj in bpy.data.objects:
    set_linear(obj)

# ── SET WORLD BACKGROUND ─────────────────────────────────────
world = bpy.context.scene.world
if world is None:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
wbg = world.node_tree.nodes.get("Background")
if wbg:
    wbg.inputs["Color"].default_value    = (0.53, 0.81, 0.92, 1.0)
    wbg.inputs["Strength"].default_value = 0.6

# ── BEAUTIFUL MATERIAL OVERRIDES (final colour pass) ─────────
# Plaster walls — warm off-white
mw = bpy.data.materials.get("M_Plaster")
if mw:
    n = mw.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.96, 0.93, 0.88, 1)
    n.inputs["Roughness"].default_value  = 0.85

# Wood floor — warm honey oak
mf = bpy.data.materials.get("M_WoodFloor")
if mf:
    n = mf.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.60, 0.38, 0.18, 1)
    n.inputs["Roughness"].default_value  = 0.55

# Roof tiles — anthracite grey (German standard)
mr = bpy.data.materials.get("M_Roof")
if mr:
    n = mr.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.12, 0.12, 0.13, 1)
    n.inputs["Roughness"].default_value  = 0.70

# Door — rich mahogany
md = bpy.data.materials.get("M_WoodDoor")
if md:
    n = md.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.30, 0.16, 0.08, 1)
    n.inputs["Roughness"].default_value  = 0.65

# Grass — vibrant green
mg = bpy.data.materials.get("M_Grass")
if mg:
    n = mg.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.22, 0.48, 0.16, 1)
    n.inputs["Roughness"].default_value  = 1.0

# Sofa — slate blue
ms = bpy.data.materials.get("M_Sofa")
if ms:
    n = ms.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.28, 0.35, 0.50, 1)
    n.inputs["Roughness"].default_value  = 0.92

# HWT tank — steel blue
mht = bpy.data.materials.get("M_HWT_Body")
if mht:
    n = mht.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.28, 0.38, 0.50, 1)
    n.inputs["Metallic"].default_value   = 0.80
    n.inputs["Roughness"].default_value  = 0.18

# Heat pump — light silver
mhp = bpy.data.materials.get("M_HPBody")
if mhp:
    n = mhp.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = (0.82, 0.84, 0.86, 1)
    n.inputs["Metallic"].default_value   = 0.60
    n.inputs["Roughness"].default_value  = 0.25

# ── RENDER SETTINGS ──────────────────────────────────────────
bpy.context.scene.render.engine      = 'CYCLES'
bpy.context.scene.cycles.samples     = 32       # fast preview
bpy.context.scene.render.fps         = FPS
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080

print()
print("="*55)
print("Animation + Colours — Complete!")
print("="*55)
print(f"Total frames: {total_frames}  ({total_frames/FPS:.0f} seconds)")
print(f"FPS: {FPS}  |  Steps: {len(sim_data)}")
print()
print("What animates:")
print("  🌡  Wall tint — blue/green/red with temperature")
print("  💧  HWT water level rises/falls with SOC")
print("  💧  HWT water colour: cold blue → hot orange")
print("  🔆  Heaters glow orange when HP is ON")
print("  🔴🟢 HP LED: green=ON, red=OFF")
print("  ☀️  Sun rises/sets in real-time")
print("  🌙  Interior lights auto-brighten at night")
print("  💡  HWT glow light pulses with charging")
print()
print(">>> Layout tab → Z → Rendered")
print(">>> SPACEBAR to play animation")
print(">>> Numpad 0 for camera view")
print("="*55)
