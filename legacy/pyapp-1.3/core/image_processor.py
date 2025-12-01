from pathlib import Path
from PIL import Image
import math


def rgb_to_lab(r, g, b):
    """Convert RGB to LAB color space."""
    # sRGB to linear RGB
    def srgb_to_linear(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    
    rl = srgb_to_linear(r)
    gl = srgb_to_linear(g)
    bl = srgb_to_linear(b)
    
    # Linear RGB to XYZ
    X = rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375
    Y = rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750
    Z = rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041
    
    # XYZ to LAB
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    xr, yr, zr = X / Xn, Y / Yn, Z / Zn
    
    def f(t):
        return t ** (1/3) if t > 0.008856 else (7.787 * t) + (16.0 / 116.0)
    
    fx, fy, fz = f(xr), f(yr), f(zr)
    L = max(0.0, 116.0 * fy - 16.0)
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    
    return (L, a, b)


def lab_to_rgb(L, a, b):
    """Convert LAB to RGB color space."""
    # LAB to XYZ
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0
    
    def f_inv(t):
        t3 = t ** 3
        return t3 if t3 > 0.008856 else (t - 16.0 / 116.0) / 7.787
    
    xr, yr, zr = f_inv(fx), f_inv(fy), f_inv(fz)
    X, Y, Z = xr * Xn, yr * Yn, zr * Zn
    
    # XYZ to linear RGB
    rl = X *  3.2404542 + Y * -1.5371385 + Z * -0.4985314
    gl = X * -0.9692660 + Y *  1.8760108 + Z *  0.0415560
    bl = X *  0.0556434 + Y * -0.2040259 + Z *  1.0572252
    
    # Linear RGB to sRGB
    def linear_to_srgb(c):
        c = max(0.0, min(1.0, c))
        v = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
        return max(0, min(255, int(round(v * 255.0))))
    
    return (linear_to_srgb(rl), linear_to_srgb(gl), linear_to_srgb(bl))


def deltaE76(lab1, lab2):
    """Calculate color difference in LAB space."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2)))


def process_image(input_path: Path, output_path: Path, settings: dict):
    """Process a single image with all transformations."""
    img = Image.open(input_path).convert("RGBA")
    px = img.load()
    w, h = img.size
    
    # Step 1: Opacity normalization
    alpha_low = settings['alpha_low_cutoff']
    alpha_high_min = settings['alpha_high_min']
    alpha_high_max = settings['alpha_high_max']
    
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            
            if a < alpha_low:
                px[x, y] = (r, g, b, 0)
            elif alpha_high_min <= a <= alpha_high_max:
                px[x, y] = (r, g, b, 255)
    
    # Step 2: Color simplification
    if settings['enable_color_simplify']:
        threshold = settings['lab_merge_threshold']
        
        # Collect unique colors
        color_counts = {}
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a >= 1:
                    key = (r, g, b)
                    color_counts[key] = color_counts.get(key, 0) + 1
        
        if color_counts:
            # Build LAB clusters
            clusters = []
            items = sorted(color_counts.items(), key=lambda kv: kv[1], reverse=True)
            
            for (r, g, b), cnt in items:
                lab = rgb_to_lab(r, g, b)
                assigned = False
                
                for c in clusters:
                    if deltaE76(lab, c['center_lab']) <= threshold:
                        c['members'].append(((r, g, b), cnt))
                        c['sumL'] += lab[0] * cnt
                        c['suma'] += lab[1] * cnt
                        c['sumb'] += lab[2] * cnt
                        c['n'] += cnt
                        c['center_lab'] = (c['sumL']/c['n'], c['suma']/c['n'], c['sumb']/c['n'])
                        assigned = True
                        break
                
                if not assigned:
                    clusters.append({
                        'center_lab': lab,
                        'sumL': lab[0] * cnt,
                        'suma': lab[1] * cnt,
                        'sumb': lab[2] * cnt,
                        'n': cnt,
                        'members': [((r, g, b), cnt)]
                    })
            
            # Build color map
            colormap = {}
            for c in clusters:
                rep = lab_to_rgb(*c['center_lab'])
                for (rgb, _) in c['members']:
                    colormap[rgb] = rep
            
            # Apply color map
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    if a >= 1:
                        rgb = (r, g, b)
                        if rgb in colormap:
                            rep = colormap[rgb]
                            px[x, y] = (rep[0], rep[1], rep[2], a)
    
    # Step 3: Outline generation
    outline_color = settings['outline_color']
    connectivity = settings['connectivity']
    thickness = settings['thickness']
    edge_cutoff = settings['edge_cutoff']
    
    # Get alpha channel
    alpha = [[px[x, y][3] for x in range(w)] for y in range(h)]
    
    # Build outline mask
    mask = [[False]*w for _ in range(h)]
    
    def get_neighbors(x, y):
        neighbors = []
        if connectivity == 4:
            if x > 0: neighbors.append((x-1, y))
            if x < w-1: neighbors.append((x+1, y))
            if y > 0: neighbors.append((x, y-1))
            if y < h-1: neighbors.append((x, y+1))
        else:  # 8
            for nx in range(max(0, x-1), min(w, x+2)):
                for ny in range(max(0, y-1), min(h, y+2)):
                    if not (nx == x and ny == y):
                        neighbors.append((nx, ny))
        return neighbors
    
    # Find border pixels
    frontier = []
    for y in range(h):
        for x in range(w):
            if alpha[y][x] > edge_cutoff:
                for nx, ny in get_neighbors(x, y):
                    if alpha[ny][nx] <= edge_cutoff:
                        mask[y][x] = True
                        frontier.append((x, y))
                        break
    
    # Grow inward for thickness
    for _ in range(1, thickness):
        new_frontier = []
        for x, y in frontier:
            for nx, ny in get_neighbors(x, y):
                if alpha[ny][nx] > edge_cutoff and not mask[ny][nx]:
                    mask[ny][nx] = True
                    new_frontier.append((nx, ny))
        frontier = new_frontier
    
    # Apply outline
    for y in range(h):
        for x in range(w):
            if mask[y][x]:
                px[x, y] = outline_color
    
    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)