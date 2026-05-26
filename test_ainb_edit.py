import unittest
from ainb.ainb import AINB
from ainb.node import Node, NodeType, get_null_index
from ainb.command import Command
from ainb.param_common import ParamType

class TestAINBEditingAPI(unittest.TestCase):
    def setUp(self):
        """Build a mock AINB graph for testing."""
        self.ainb = AINB()
        
        self.node0 = Node(NodeType.UserDefined)
        self.node0.name = "StartNode"
        
        self.node1 = Node(NodeType.Element_S32Selector)
        self.node1.name = "SelectorNode"
        
        self.node2 = Node(NodeType.UserDefined)
        self.node2.name = "ActionNode"

        # Add Nodes
        self.ainb.add_node(self.node0) # Index 0
        self.ainb.add_node(self.node1) # Index 1
        self.ainb.add_node(self.node2) # Index 2

        # Wire Control Flow: 0 -> 1 -> 2
        self.node0.link_child(self.node1, "Next")
        self.node1.link_child(self.node2, "Match", condition=42)

        # Wire Parameters
        param = self.node2.add_input_param(ParamType.Int, "TargetCount", default_value=1)
        self.node2.set_input_from_node(ParamType.Int, "TargetCount", self.node0, 0)

        # Add a Command referencing Node 0
        self.ainb.add_command("Main", root_node=self.node0)

    # ==========================================
    # TESTS: NODE GRAPH MANAGEMENT
    # ==========================================

    def test_add_node(self):
        n3 = Node(NodeType.UserDefined)
        idx = self.ainb.add_node(n3)
        self.assertEqual(idx, 3)
        self.assertEqual(len(self.ainb.nodes), 4)

    def test_remove_node_index_shifting(self):
        self.ainb.remove_node(1)
        self.assertEqual(len(self.ainb.nodes), 2)
        self.assertEqual(self.ainb.nodes[1].name, "ActionNode")
        self.assertEqual(self.ainb.nodes[1].index, 1)
        self.assertEqual(self.node0.child_plugs[0].node_index, get_null_index())

        target_param = self.ainb.nodes[1].params.get_inputs(ParamType.Int)[0]
        self.assertEqual(target_param.source.src_node_index, 0)

    def test_remove_root_node(self):
        self.ainb.remove_node(0)
        self.assertEqual(self.ainb.commands[0].root_node_index, -1)
        
        target_param = self.ainb.nodes[1].params.get_inputs(ParamType.Int)[0]
        self.assertEqual(target_param.source.src_node_index, -1)

    def test_insert_node_index_shifting(self):
        n_new = Node(NodeType.UserDefined)
        n_new.name = "InjectedNode"
        self.ainb.insert_node(1, n_new)

        self.assertEqual(self.ainb.nodes[1].name, "InjectedNode")
        self.assertEqual(self.node1.index, 2) 
        self.assertEqual(self.node2.index, 3) 

        self.assertEqual(self.node0.child_plugs[0].node_index, 2)
        self.assertEqual(self.node1.child_plugs[0].node_index, 3)

        target_param = self.ainb.nodes[3].params.get_inputs(ParamType.Int)[0]
        self.assertEqual(target_param.source.src_node_index, 0)

    def test_polymorphic_link_child(self):
        self.assertEqual(len(self.node1.child_plugs), 1)
        plug = self.node1.child_plugs[0]
        
        from ainb.node import S32SelectorPlug
        self.assertIsInstance(plug, S32SelectorPlug)
        self.assertEqual(plug.condition, 42)

    # ==========================================
    # TESTS: COMMANDS AND MODULES
    # ==========================================

    def test_commands(self):
        self.assertEqual(len(self.ainb.commands), 1)
        
        # Add Command
        cmd = self.ainb.add_command("Idle", root_node=self.node1)
        self.assertEqual(len(self.ainb.commands), 2)
        self.assertEqual(cmd.name, "Idle")
        self.assertEqual(cmd.root_node_index, self.node1.index)
        self.assertIsNotNone(cmd.guid)
        
        # Remove Command
        self.ainb.remove_command("Main")
        self.assertEqual(len(self.ainb.commands), 1)
        self.assertEqual(self.ainb.commands[0].name, "Idle")

    def test_modules(self):
        self.assertEqual(len(self.ainb.modules), 0)
        
        # Add Module
        self.ainb.add_module("logic/Player.ainb", "Logic")
        self.assertEqual(len(self.ainb.modules), 1)
        self.assertEqual(self.ainb.modules[0].path, "logic/Player.ainb")
        self.assertEqual(self.ainb.modules[0].category, "Logic")
        
        # Remove Module
        self.ainb.remove_module("logic/Player.ainb")
        self.assertEqual(len(self.ainb.modules), 0)

    # ==========================================
    # TESTS: BLACKBOARD
    # ==========================================
        
    def test_blackboard_wiring_and_shifting(self):
        # Create 3 Blackboard parameters
        idx0 = self.ainb.add_blackboard_param(ParamType.Int, "Counter1", 0)
        idx1 = self.ainb.add_blackboard_param(ParamType.Int, "Counter2", 10)
        idx2 = self.ainb.add_blackboard_param(ParamType.Int, "Counter3", 20)
        
        self.assertEqual(idx0, 0)
        self.assertEqual(idx1, 1)
        self.assertEqual(idx2, 2)
        
        # Wire ActionNode to the last parameter (idx2)
        self.node2.set_input_from_blackboard(ParamType.Int, "TargetCount", idx2)
        param = self.node2.params.get_inputs(ParamType.Int)[0]
        
        self.assertTrue(param.is_blackboard_input)
        self.assertEqual(param.source.flags.get_index(), 2)

        # Remove the middle parameter (idx1). 
        # This should shift the reference in ActionNode down from 2 to 1.
        self.ainb.remove_blackboard_param(ParamType.Int, 1)
        self.assertEqual(param.source.flags.get_index(), 1)
        
        # Remove the parameter ActionNode is now pointing to.
        # This should nullify the connection and revert it to a default state.
        self.ainb.remove_blackboard_param(ParamType.Int, 1)
        self.assertFalse(param.is_blackboard_input)

    # ==========================================
    # TESTS: NODE DEFAULTS, ATTACHMENTS, PROPS
    # ==========================================

    def test_update_input_default(self):
        # Originally, TargetCount is wired to Node0
        param = self.node2.params.get_inputs(ParamType.Int)[0]
        self.assertEqual(param.source.src_node_index, 0)

        # Update it to rely on a hardcoded default value instead
        self.node2.update_input_default(ParamType.Int, "TargetCount", 99)
        
        self.assertEqual(param.default_value, 99)
        self.assertEqual(param.source.src_node_index, -1)
        self.assertFalse(param.is_blackboard_input)

    def test_node_attachments_and_properties(self):
        # Attachments
        self.assertEqual(len(self.node2.attachments), 0)
        att = self.node2.add_attachment("TestAttachment")
        self.assertEqual(len(self.node2.attachments), 1)
        self.assertEqual(self.node2.attachments[0].name, "TestAttachment")
        
        self.node2.remove_attachment("TestAttachment")
        self.assertEqual(len(self.node2.attachments), 0)

        # Properties
        self.assertEqual(len(self.node2.properties.get_properties(ParamType.Float)), 0)
        prop = self.node2.add_property(ParamType.Float, "DetectionRadius", 15.5)
        
        self.assertEqual(len(self.node2.properties.get_properties(ParamType.Float)), 1)
        self.assertEqual(prop.name, "DetectionRadius")
        self.assertEqual(prop.default_value, 15.5)

if __name__ == '__main__':
    unittest.main()