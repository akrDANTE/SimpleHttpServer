import random
import logging
from typing import List

class RobustUIExplorer:
    def __init__(self, device: DeviceInterface, state_manager: StateManager):
        self.device = device
        self.state_manager = state_manager
        
        self.POSSIBLE_ACTIONS = [
            "click_center", "click_bottom", "swipe_up", 
            "swipe_down", "swipe_left", "swipe_right"
        ]
        
        self.stack: List[str] = []
        self.pending_targets: List[str] = []

    def resume_exploration(self, max_steps: int = 1000):
        logging.info("--- Booting Crawler & Recovering State ---")
        
        # 1. Rebuild the exploration queue from Kuzu DB
        frontier_nodes = self.state_manager.get_frontier_states(self.POSSIBLE_ACTIONS)
        self.pending_targets.extend(frontier_nodes)
        
        logging.info(f"Recovered {len(frontier_nodes)} unexplored/partially-explored states from Kuzu DB.")

        # 2. Boot the app to establish our starting reality
        self.device.restart_app()
        self.device.wait_for_settle()
        actual_root = self.device.get_state_hash()
        
        self.state_manager.add_state_if_new(actual_root)
        
        # We always push our current location to the stack first so we explore 
        # outward from where we landed, minimizing immediate heavy path-replaying.
        self.stack.append(actual_root)

        steps = 0
        while (self.stack or self.pending_targets) and steps < max_steps:
            steps += 1
            
            # 3. Pull from recovered DB targets if local stack is empty
            if not self.stack and self.pending_targets:
                next_target = self.pending_targets.pop()
                logging.info(f"Local stack empty. Popping recovered target: {next_target[:6]}")
                self.stack.append(next_target)

            target_state = self.stack.pop()
            
            # 4. Navigate to the state (handles multi-root and environment failures)
            success = self._navigate_to(target_state)
            if not success:
                # If navigation failed, _navigate_to has already appended the unexpected 
                # new states to self.stack or self.pending_targets. We just loop again.
                continue

            # 5. Check what actions are left for this state
            unperformed = self.state_manager.get_unperformed_actions(target_state, self.POSSIBLE_ACTIONS)
            
            if not unperformed:
                logging.info(f"State {target_state[:6]} is now fully explored.")
                continue

            # 6. Choose and execute a random unperformed action
            action = random.choice(unperformed)
            logging.info(f"Step {steps}: Executing '{action}' from state {target_state[:6]}")

            self.device.execute_action(action)
            self.device.wait_for_settle()
            new_state = self.device.get_state_hash()

            # 7. Persist to Kuzu instantly (This makes crash recovery possible)
            self.state_manager.add_state_if_new(new_state)
            self.state_manager.add_edge(target_state, action, new_state)

            # 8. Manage queues
            if len(unperformed) > 1:
                self.stack.append(target_state) # Still more to do here, put it back
            
            self.stack.append(new_state) # Dive deeper into the newly discovered state

        logging.info("Exploration session finished or max steps reached.")

    def _navigate_to(self, target_state: str) -> bool:
        """
        Attempts to put the app into the target_state. 
        Returns True if successful, False if interrupted by environment or new root.
        """
        current_state = self.device.get_state_hash()
        if current_state == target_state:
            return True

        logging.info(f"Attempting to replay path to reach target state: {target_state[:6]}")
        
        # Need to guarantee a clean path start
        self.device.restart_app()
        self.device.wait_for_settle()
        actual_root = self.device.get_state_hash()
        self.state_manager.add_state_if_new(actual_root)

        # Query Kuzu for the shortest path from our current reality
        path = self.state_manager.get_shortest_path(actual_root, target_state)

        if not path:
            logging.warning(f"No path from root {actual_root[:6]} to {target_state[:6]}. Pivoting.")
            self.pending_targets.append(target_state)
            self.stack.append(actual_root)
            return False

        # Execute the path replay
        current_replay_state = actual_root
        for expected_state, action in path:
            self.device.execute_action(action)
            self.device.wait_for_settle()
            new_observed_state = self.device.get_state_hash()

            if new_observed_state != expected_state:
                logging.warning(f"Path broken during replay! Expected {expected_state[:6]}, got {new_observed_state[:6]}")
                
                # Immediately persist the anomaly to Kuzu so it is not lost if we crash right now
                self.state_manager.add_state_if_new(new_observed_state)
                self.state_manager.add_edge(current_replay_state, action, new_observed_state)
                
                self.pending_targets.append(target_state) 
                self.stack.append(new_observed_state)
                return False
            
            current_replay_state = new_observed_state

        return True
      
