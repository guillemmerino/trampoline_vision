"""Solver hongarès rectangular, determinista i sense dependències opcionals."""

import math


def linear_assignment(costs):
    """Minimitza costos finits; exigeix almenys una columna per fila, sense mutar-los."""
    n=len(costs)
    if not n:
        return ()
    m=len(costs[0])
    if m < n or any(len(row)!=m or any(type(c) not in (int,float) or not math.isfinite(c) for c in row) for row in costs):
        raise ValueError('Hungarian requires finite rectangular costs with rows <= columns')
    u, v, p, way=[0.]*(n+1), [0.]*(m+1), [0]*(m+1), [0]*(m+1)
    for row in range(1,n+1):
        p[0]=row
        j0=0
        minimum, used=[math.inf]*(m+1), [False]*(m+1)
        while True:
            used[j0]=True
            i0=p[j0]
            delta, j1=math.inf, 0
            for j in range(1,m+1):
                if not used[j]:
                    current=costs[i0-1][j-1]-u[i0]-v[j]
                    if current < minimum[j]:
                        minimum[j], way[j]=current,j0
                    if minimum[j] < delta:
                        delta,j1=minimum[j],j
            for j in range(m+1):
                if used[j]:
                    u[p[j]]+=delta
                    v[j]-=delta
                else:
                    minimum[j]-=delta
            j0=j1
            if p[j0]==0:
                break
        while True:
            j1=way[j0]
            p[j0]=p[j1]
            j0=j1
            if j0==0:
                break
    result=[-1]*n
    for j in range(1,m+1):
        if p[j]:
            result[p[j]-1]=j-1
    return tuple(result)
