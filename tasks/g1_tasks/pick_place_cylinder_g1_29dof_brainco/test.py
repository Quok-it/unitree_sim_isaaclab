cd /home/code/unitree_sim_isaaclab
python -c "
from isaacsim import SimulationApp
app = SimulationApp({'headless': True})

from omni.isaac.core.articulations import Articulation
from omni.isaac.core import World
from pxr import Usd, UsdGeom

world = World()
world.scene.add_default_ground_plane()

import omni.usd
stage = omni.usd.get_context().get_stage()
prim = stage.DefinePrim('/Robot', 'Xform')
prim.GetReferences().AddReference('assets/robots/g1-29dof-brainco-base-fix-usd/g1_29dof_with_brainco.usd')

world.reset()

art = Articulation('/Robot')
art.initialize()
print(f'Num DOFs: {art.num_dof}')
print(f'DOF names: {art.dof_names}')

app.close()
"
