"""Enumerate the REAL runtime API surface and diff it against the shipped type stub.

The Controller class is empty outside the sandbox -- only the live object handed to run() carries the
Rust-injected methods. fcode/_types.py's TYPE_CHECKING stub is what every human and every type checker
reads, so any divergence between it and the live object is a documentation error by definition.

This probe hardcodes the stub's 81 method names, the stub's GameConstants fields and their values, and
the stub's enum members, then reports ONLY the differences plus a few counts. A clean run is a short
message; anything long is a finding.

Reported through ct.resign() -- print() is swallowed (G29). Budget: resign_message truncates at 500 (M06).
"""

from fcode import (Controller, Direction, Environment, EntityType, GameConstants, GameError,
                   Position, ResourceType, Team)

STUB = (
    "build,build_barrier,build_conveyor,build_gunner,build_harvester,build_launcher,build_sentinel,"
    "build_splitter,can_act,can_build,can_build_barrier,can_build_conveyor,can_build_gunner,"
    "can_build_harvester,can_build_launcher,can_build_sentinel,can_build_splitter,can_convert_ammo,"
    "can_destroy,can_fire,can_fire_from,can_heal,can_launch,can_move,can_rotate,can_spawn,"
    "convert_ammo,destroy,draw_indicator_dot,draw_indicator_line,fire,get_action_cooldown,"
    "get_attackable_tiles,get_attackable_tiles_from,get_barrier_cost,get_builder_bot_cost,"
    "get_conveyor_cost,get_cpu_time_elapsed,get_current_round,get_direction,get_entity_type,"
    "get_global_ammo,get_global_resources,get_gunner_cost,get_gunner_target,get_harvester_cost,"
    "get_hp,get_id,get_launcher_cost,get_map_height,get_map_width,get_max_hp,get_move_cooldown,"
    "get_nearby_buildings,get_nearby_entities,get_nearby_tiles,get_nearby_units,get_position,"
    "get_scale_percent,get_sentinel_cost,get_splitter_cost,get_stored_resource,"
    "get_stored_resource_id,get_team,get_tile_builder_bot_id,get_tile_building_id,get_tile_env,"
    "get_unit_count,get_vision_radius_sq,heal,is_in_vision,is_tile_empty,is_tile_passable,launch,"
    "move,read_store,resign,rotate,self_destruct,spawn_builder,write_store"
).split(",")

# GameConstants fields as declared in fcode/_types.py, name=value.
STUB_CONST = (
    "MAX_TURNS=1000,STACK_SIZE=10,STARTING_TITANIUM=500,MAX_TEAM_UNITS=50,"
    "PASSIVE_TITANIUM_AMOUNT=10,PASSIVE_TITANIUM_INTERVAL=4,CORE_SPAWNING_RADIUS_SQ=2,"
    "CORE_ACTION_RADIUS_SQ=8,CORE_VISION_RADIUS_SQ=36,BUILDER_BOT_VISION_RADIUS_SQ=20,"
    "GUNNER_VISION_RADIUS_SQ=13,SENTINEL_VISION_RADIUS_SQ=32,LAUNCHER_VISION_RADIUS_SQ=26,"
    "CONVEYOR_BASE_COST=3,SPLITTER_BASE_COST=6,HARVESTER_BASE_COST=20,BARRIER_BASE_COST=3,"
    "GUNNER_BASE_COST=10,SENTINEL_BASE_COST=30,LAUNCHER_BASE_COST=20,BUILDER_BOT_BASE_COST=30,"
    "GUNNER_ROTATE_COST=10,GUNNER_ROTATE_COOLDOWN=1,CONVEYOR_MAX_HP=20,SPLITTER_MAX_HP=20,"
    "HARVESTER_MAX_HP=30,BARRIER_MAX_HP=30,STORE_SIZE=16,BUILDER_BOT_MAX_HP=40,CORE_MAX_HP=500,"
    "GUNNER_MAX_HP=40,SENTINEL_MAX_HP=30,LAUNCHER_MAX_HP=30,BUILDER_BOT_SELF_DESTRUCT_DAMAGE=0,"
    "BUILDER_BOT_ATTACK_DAMAGE=2,BUILDER_BOT_ATTACK_COST=2,BUILDER_BOT_HEAL_COST=1,HEAL_AMOUNT=4,"
    "GUNNER_DAMAGE=10,GUNNER_FIRE_COOLDOWN=1,GUNNER_AMMO_COST=2,SENTINEL_DAMAGE=18,"
    "SENTINEL_FIRE_COOLDOWN=3,SENTINEL_AMMO_COST=10,LAUNCHER_FIRE_COOLDOWN=1"
).split(",")

STUB_ENUM = {
    "EntityType": "BARRIER,BUILDER_BOT,CONVEYOR,CORE,GUNNER,HARVESTER,LAUNCHER,SENTINEL,SPLITTER",
    "Direction": "CENTRE,EAST,NORTH,NORTHEAST,NORTHWEST,SOUTH,SOUTHEAST,SOUTHWEST,WEST",
    "Environment": "EMPTY,ORE_TITANIUM,WALL",
    "Team": "A,B",
    "ResourceType": "TITANIUM",
}


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("EXC:" + type(exc).__name__ + ":" + str(exc)[:90])
            except Exception:
                pass

    def _run(self, ct):
        if self.done:
            return
        self.done = True
        p = []

        live = sorted(n for n in dir(ct) if not n.startswith("_"))
        extra = [n for n in live if n not in STUB]
        missing = [n for n in STUB if n not in live]
        p.append("CTRL n=%d extra=%s missing=%s" % (len(live),
                                                    ",".join(extra) or "-",
                                                    ",".join(missing) or "-"))

        # Non-callable attributes on the live controller would be data we never look at.
        noncall = [n for n in live if not callable(getattr(ct, n, None))]
        p.append("noncall=%s" % (",".join(noncall) or "-"))

        # GameConstants: field set + value diff against the stub.
        gcnames = sorted(n for n in dir(GameConstants) if not n.startswith("_"))
        stubnames = [kv.split("=")[0] for kv in STUB_CONST]
        cextra = [n for n in gcnames if n not in stubnames]
        cmiss = [n for n in stubnames if n not in gcnames]
        vdiff = []
        for kv in STUB_CONST:
            k, v = kv.split("=")
            got = getattr(GameConstants, k, None)
            if got is not None and str(got) != v:
                vdiff.append("%s:%s!=%s" % (k, got, v))
        p.append("GC n=%d extra=%s miss=%s vdiff=%s" % (len(gcnames),
                                                        ",".join(cextra) or "-",
                                                        ",".join(cmiss) or "-",
                                                        ",".join(vdiff) or "-"))

        for cls in (EntityType, Direction, Environment, Team, ResourceType):
            got = sorted(m.name for m in cls)
            want = STUB_ENUM[cls.__name__].split(",")
            d = [n for n in got if n not in want] + ["-" + n for n in want if n not in got]
            if d:
                p.append("%s DIFF %s" % (cls.__name__, ",".join(d)))

        # GameError: bare Exception subclass, or does it carry subclasses / extra fields?
        subs = sorted(c.__name__ for c in GameError.__subclasses__())
        p.append("GE base=%s subs=%s" % (GameError.__bases__[0].__name__, ",".join(subs) or "-"))

        ct.resign(" | ".join(p))
