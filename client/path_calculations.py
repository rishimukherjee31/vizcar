import numpy as np

# ============================================================
#   HELPER FUNCTIONS
# ============================================================

def heading_from_points(p1, p2):
    """
    Compute the heading angle between p1 -> p2.
    Returns heading in radians (range -pi to +pi)
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return float(np.arctan2(dy, dx))

def path_with_headings(path):
    """
    Given a list/array of (x,y) points, compute heading for each segment.
    Returns a list of dicts: {"x": x, "y": y, "heading": theta}
    """
    pts = np.array(path)
    result = []

    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i+1]

        heading = heading_from_points((x1, y1), (x2, y2))

        result.append({
            "point": (float(x1), float(y1)),
            "heading": float(heading)
        })

    # Last point has NO heading
    x_last, y_last = pts[-1]
    result.append({
        "point": (float(x_last), float(y_last)),
        "heading": None      # or remove this field entirely
    })

    return result


def uniform_t(n):
    """Generate n evenly spaced parameters from 0…1 inclusive."""
    return np.linspace(0, 1, n)


# ============================================================
#   1. POINT-TO-POINT PATH (straight line)
# ============================================================

def point_path(p_start, p_end, n=50):
    """
    Simple straight-line path from p_start → p_end.
    Returns array of shape (n,2).
    """
    p_start = np.array(p_start, dtype=float)
    p_end   = np.array(p_end,   dtype=float)

    t = uniform_t(n)
    pts = p_start[None,:] * (1 - t[:,None]) + p_end[None,:] * t[:,None]
    return pts


# ============================================================
#   2. LINEAR MULTI-SEGMENT PATH
# ============================================================

def linear_path(points, n=50):
    """
    Connect waypoints with straight lines.
    points = [(x,y), (x,y), ...]
    Returns an Nx2 array of concatenated segments.
    """
    pts = np.array(points, dtype=float)
    segments = []

    for i in range(len(pts)-1):
        p1 = pts[i]
        p2 = pts[i+1]

        seg = point_path(p1, p2, n)

        # remove duplicate start on segments > 0
        if i > 0:
            seg = seg[1:]

        segments.append(seg)

    if len(segments):
        return np.vstack(segments)
    else:
        return pts


# ============================================================
#   3. CATMULL–ROM SPLINE
# ============================================================

def catmull_path(points, n=50):
    """
    Catmull–Rom spline through all waypoints.
    Requires at least 4 points.
    Returns Nx2 array of samples.
    """
    pts = np.array(points, dtype=float)
    if len(pts) < 4:
        return linear_path(points, n)

    out = []
    for i in range(len(pts)-3):
        P0, P1, P2, P3 = pts[i:i+4]

        t = uniform_t(n)
        t2 = t*t
        t3 = t*t*t

        # Catmull-Rom equation (x and y handled together)
        M = 0.5 * (
            (2*P1)[None,:]
            + (-P0 + P2)[None,:] * t[:,None]
            + (2*P0 - 5*P1 + 4*P2 - P3)[None,:] * t2[:,None]
            + (-P0 + 3*P1 - 3*P2 + P3)[None,:] * t3[:,None]
        )

        if i > 0:
            M = M[1:]

        out.append(M)

    return np.vstack(out)


# ============================================================
#   4. CUBIC HERMITE SPLINE (smooth)
# ============================================================

def cubic_path(points, n=50):
    """
    Smooth cubic Hermite spline through waypoints.
    Uses tangent estimates.
    """
    pts = np.array(points, dtype=float)
    if len(pts) < 2:
        return pts

    # Estimate tangents (finite difference)
    tangents = np.zeros_like(pts)
    tangents[1:-1] = (pts[2:] - pts[:-2]) / 2
    tangents[0] = pts[1] - pts[0]
    tangents[-1] = pts[-1] - pts[-2]

    out = []
    for i in range(len(pts)-1):
        P0 = pts[i]
        P1 = pts[i+1]
        T0 = tangents[i]
        T1 = tangents[i+1]

        t = uniform_t(n)
        t2 = t*t
        t3 = t*t*t

        h00 = 2*t3 - 3*t2 + 1
        h10 = t3 - 2*t2 + t
        h01 = -2*t3 + 3*t2
        h11 = t3 - t2

        M = (
            h00[:,None]*P0
            + h10[:,None]*T0
            + h01[:,None]*P1
            + h11[:,None]*T1
        )

        if i > 0:
            M = M[1:]

        out.append(M)

    return np.vstack(out)


# ============================================================
#   5. BÉZIER CURVE (4 control points)
# ============================================================

# def bezier_path(P0, P1, P2, P3, n=50):
#     """
#     Cubic Bézier curve from 4 control points.
#     Returns Nx2 array.
#     """
#     P0 = np.array(P0, dtype=float)
#     P1 = np.array(P1, dtype=float)
#     P2 = np.array(P2, dtype=float)
#     P3 = np.array(P3, dtype=float)

#     t = uniform_t(n)
#     u = 1 - t

#     B = (
#         (u*u*u)[:,None]*P0 +
#         (3*u*u*t)[:,None]*P1 +
#         (3*u*t*t)[:,None]*P2 +
#         (t*t*t)[:,None]*P3
#     )
#     return B

def bezier_segment(P0, P1, P2, P3, n=50):
    t = np.linspace(0, 1, n)
    x = (1-t)**3 * P0[0] + 3*(1-t)**2*t * P1[0] + 3*(1-t)*t**2 * P2[0] + t**3 * P3[0]
    y = (1-t)**3 * P0[1] + 3*(1-t)**2*t * P1[1] + 3*(1-t)*t**2 * P2[1] + t**3 * P3[1]
    return np.column_stack((x, y))

def bezier_chained(points, n=50):
    pts = np.array(points)
    if len(pts) < 4:
        return pts  # need at least 4 points

    path = []
    # process groups of 4 with overlap of 1 point
    for i in range(0, len(pts)-3, 3):
        P0, P1, P2, P3 = pts[i:i+4]
        seg = bezier_segment(P0, P1, P2, P3, n=n)

        if i > 0:
            seg = seg[1:]

        path.append(seg)

    return np.vstack(path)