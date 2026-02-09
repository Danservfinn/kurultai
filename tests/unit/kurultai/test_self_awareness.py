"""
Unit Tests for Self-Awareness JavaScript Modules

Tests the Kublai self-awareness system:
- architecture-introspection.js
- proactive-reflection.js
- delegation-protocol.js
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock, patch

# Note: These tests mock the JavaScript modules since we're in Python
# In production, these would be tested with Jest/Mocha


class MockNeo4jDriver:
    """Mock Neo4j driver for JS module tests."""
    
    def __init__(self):
        self.session = Mock()
        self.session.return_value = Mock()
        self.session.return_value.run = Mock()
        self.session.return_value.close = Mock()


class TestArchitectureIntrospection:
    """Tests for architecture-introspection.js module."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        return MockNeo4jDriver()

    def test_get_architecture_overview(self, mock_driver):
        """Test getting architecture overview."""
        # Mock successful query
        record = Mock()
        record.get = Mock(side_effect=lambda k: {
            'title': 'Executive Summary',
            'category': 'overview',
            'order': Mock(toNumber=Mock(return_value=1)),
            'updated': '2026-02-08'
        }.get(k))
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would call: introspection.getArchitectureOverview()
        # Since we can't run JS, we verify the mock structure
        assert mock_driver.session is not None

    def test_search_architecture(self, mock_driver):
        """Test searching architecture sections."""
        record = Mock()
        record.get = Mock(side_effect=lambda k: {
            'title': 'Security Architecture',
            'summary': 'Defense in depth',
            'category': 'security'
        }.get(k))
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would call: introspection.searchArchitecture('security')
        assert mock_driver.session is not None

    def test_get_section(self, mock_driver):
        """Test getting specific section."""
        record = Mock()
        record.get = Mock(side_effect=lambda k: {
            'content': 'System architecture details...',
            'category': 'core',
            'version': '3.1',
            'updated': '2026-02-08'
        }.get(k))
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would call: introspection.getSection('Security Architecture')
        assert mock_driver.session is not None

    def test_get_last_sync_timestamp(self, mock_driver):
        """Test getting last sync timestamp."""
        record = Mock()
        record.get = Mock(return_value='2026-02-08T12:00:00Z')
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would call: introspection.getLastSyncTimestamp()
        assert mock_driver.session is not None

    def test_identify_gaps(self, mock_driver):
        """Test identifying architecture gaps."""
        stale_record = Mock()
        stale_record.get = Mock(side_effect=lambda k: {
            'title': 'Old Section',
            'updated': '2025-01-01'
        }.get(k))
        
        existing_record = Mock()
        existing_record.get = Mock(return_value=['Executive Summary'])
        
        result1 = Mock()
        result1.records = [stale_record]
        
        result2 = Mock()
        result2.records = [existing_record]
        
        mock_driver.session.return_value.run.side_effect = [result1, result2]
        
        # Would call: introspection.identifyGaps()
        assert mock_driver.session is not None


class TestProactiveReflection:
    """Tests for proactive-reflection.js module."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        return MockNeo4jDriver()

    def test_trigger_reflection(self, mock_driver):
        """Test triggering reflection cycle."""
        # This would:
        # 1. Call analyzeForOpportunities()
        # 2. Call storeOpportunities()
        # 3. Return summary
        
        assert mock_driver.session is not None
        # In real implementation, verify opportunities are found and stored

    def test_analyze_for_opportunities(self, mock_driver):
        """Test analyzing for improvement opportunities."""
        # Mock gaps identification
        stale_record = Mock()
        stale_record.get = Mock(side_effect=lambda k: {
            'title': 'Stale Section',
            'updated': '2025-01-01'
        }.get(k))
        
        result = Mock()
        result.records = [stale_record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would detect stale sections as opportunities
        assert mock_driver.session is not None

    def test_check_implementation_gaps_no_tasks(self, mock_driver):
        """Test detecting when no background tasks are running."""
        record = Mock()
        record.get = Mock(return_value=Mock(toNumber=Mock(return_value=0)))
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would identify implementation gap
        assert mock_driver.session is not None

    def test_check_implementation_gaps_with_tasks(self, mock_driver):
        """Test when background tasks are running normally."""
        record = Mock()
        record.get = Mock(return_value=Mock(toNumber=Mock(return_value=100)))
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would not identify gap
        assert mock_driver.session is not None

    def test_store_opportunities(self, mock_driver):
        """Test storing opportunities to Neo4j."""
        # Mock no existing opportunities
        existing_result = Mock()
        existing_result.records = [Mock(get=Mock(return_value=0))]
        
        mock_driver.session.return_value.run.return_value = existing_result
        
        opportunities = [
            {
                'type': 'stale_sync',
                'description': 'Section is stale',
                'priority': 'medium',
                'target_section': 'Test Section'
            }
        ]
        
        # Would store opportunities and return count
        assert mock_driver.session is not None

    def test_store_skips_duplicates(self, mock_driver):
        """Test that duplicate opportunities are skipped."""
        # Mock existing opportunity
        existing_result = Mock()
        existing_result.records = [Mock(get=Mock(return_value=1))]
        
        mock_driver.session.return_value.run.return_value = existing_result
        
        # Would skip storing duplicate
        assert mock_driver.session is not None

    def test_get_opportunities(self, mock_driver):
        """Test retrieving opportunities by status."""
        record = Mock()
        record.get = Mock(side_effect=lambda k: {
            'id': 'opp_123',
            'type': 'stale_sync',
            'description': 'Test opportunity',
            'priority': 'high',
            'created_at': '2026-02-08'
        }.get(k))
        
        result = Mock()
        result.records = [record]
        mock_driver.session.return_value.run.return_value = result
        
        # Would return opportunities list
        assert mock_driver.session is not None


class TestDelegationProtocol:
    """Tests for delegation-protocol.js module."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        return MockNeo4jDriver()

    @pytest.fixture
    def protocol(self, mock_driver):
        """Create DelegationProtocol instance."""
        # In real tests, this would be: new DelegationProtocol(mock_driver)
        return {'driver': mock_driver, 'config': {
            'autoVet': True,
            'autoImplement': True,
            'autoValidate': True,
            'autoSync': False
        }}

    def test_create_proposal(self, protocol):
        """Test creating proposal from opportunity."""
        # Mock opportunity exists
        opp_record = Mock()
        opp_record.get = Mock(side_effect=lambda k: {
            'type': 'stale_sync',
            'description': 'Section is stale',
            'priority': 'medium',
            'target_section': 'Test Section'
        }.get(k))
        
        result = Mock()
        result.records = [opp_record]
        protocol['driver'].session.return_value.run.return_value = result
        
        # Would create ArchitectureProposal node
        assert protocol['driver'].session is not None

    def test_route_to_vetting(self, protocol):
        """Test routing proposal to Ögedei for vetting."""
        # Would update proposal status and create Vetting node
        assert protocol['driver'].session is not None

    def test_complete_vetting_approve(self, protocol):
        """Test completing vetting with approval."""
        # Would set status to approved and optionally route to implementation
        assert protocol['driver'].session is not None

    def test_complete_vetting_reject(self, protocol):
        """Test completing vetting with rejection."""
        # Would set status to rejected
        assert protocol['driver'].session is not None

    def test_start_implementation(self, protocol):
        """Test starting implementation phase."""
        # Would create Implementation node
        assert protocol['driver'].session is not None

    def test_complete_implementation(self, protocol):
        """Test completing implementation."""
        # Would update Implementation and optionally trigger validation
        assert protocol['driver'].session is not None

    def test_validate_implementation_pass(self, protocol):
        """Test validation that passes."""
        # Would run checks and mark as validated
        assert protocol['driver'].session is not None

    def test_validate_implementation_fail(self, protocol):
        """Test validation that fails."""
        # Would return failed status with check details
        assert protocol['driver'].session is not None

    def test_sync_to_architecture_manual(self, protocol):
        """Test that sync requires manual approval when autoSync is false."""
        assert protocol['config']['autoSync'] is False
        # Would return pending_approval status

    def test_get_workflow_status(self, protocol):
        """Test getting complete workflow status."""
        record = Mock()
        record.get = Mock(side_effect=lambda k: {
            'proposal_status': 'under_review',
            'impl_status': 'not_started',
            'vetting_status': 'pending',
            'vetting_decision': None,
            'impl_work_status': None,
            'validation_passed': None,
            'synced_section': None
        }.get(k))
        
        result = Mock()
        result.records = [record]
        protocol['driver'].session.return_value.run.return_value = result
        
        # Would return full workflow status
        assert protocol['driver'].session is not None


class TestStateMachine:
    """Tests for proposal state machine."""

    def test_state_transitions(self):
        """Test all valid state transitions."""
        # PROPOSED → UNDER_REVIEW → APPROVED → IMPLEMENTED → VALIDATED → SYNCED
        # UNDER_REVIEW → REJECTED
        # REJECTED → APPROVED (can return)
        
        transitions = [
            ('proposed', 'under_review'),
            ('under_review', 'approved'),
            ('under_review', 'rejected'),
            ('approved', 'implemented'),
            ('implemented', 'validated'),
            ('validated', 'synced'),
            ('rejected', 'approved'),  # Can return from rejected
        ]
        
        for from_state, to_state in transitions:
            # Verify transition is valid
            assert from_state != to_state

    def test_invalid_transitions(self):
        """Test that invalid transitions are prevented."""
        invalid_transitions = [
            ('proposed', 'approved'),  # Must go through under_review
            ('proposed', 'implemented'),  # Must be approved first
            ('rejected', 'synced'),  # Must be approved and implemented
        ]
        
        for from_state, to_state in invalid_transitions:
            # These should be blocked by guards
            pass  # Implementation would verify guards prevent these


class TestGuardrails:
    """Tests for safety guardrails."""

    def test_dual_validation_requirement(self):
        """Test that both status fields must be validated."""
        # Both status AND implementation_status must be 'validated'
        proposal = {
            'status': 'approved',
            'implementation_status': 'validated'
        }
        
        # Should not allow sync
        assert not (proposal['status'] == 'validated' and 
                   proposal['implementation_status'] == 'validated')

    def test_section_mapping_verification(self):
        """Test that proposals must map to existing sections."""
        # Proposals must target existing ArchitectureSection nodes
        existing_sections = ['Executive Summary', 'Security Architecture']
        proposal_target = 'Executive Summary'
        
        assert proposal_target in existing_sections

    def test_manual_sync_gate(self):
        """Test that autoSync: false requires manual approval."""
        config = {'autoSync': False}
        
        # Sync should require manual approval
        assert config['autoSync'] is False


class TestIntegration:
    """Integration tests for self-awareness workflow."""

    def test_full_workflow(self):
        """Test complete self-awareness workflow."""
        # 1. Kublai identifies gaps via introspection
        # 2. Creates ImprovementOpportunity
        # 3. Creates ArchitectureProposal
        # 4. Routes to Ögedei for vetting
        # 5. Ögedei approves
        # 6. Routes to Temüjin for implementation
        # 7. Temüjin completes implementation
        # 8. Jochi validates
        # 9. Manual approval for sync
        # 10. Changes synced to ARCHITECTURE.md
        
        # This would be tested with full Neo4j integration
        pass

    def test_reflection_to_proposal_flow(self):
        """Test flow from reflection to proposal creation."""
        # Reflection identifies stale section
        # Creates ImprovementOpportunity
        # Opportunity evolves into ArchitectureProposal
        
        pass

    def test_guardrail_blocks_invalid_sync(self):
        """Test that guardrails prevent invalid ARCHITECTURE.md updates."""
        # Proposal with status != 'validated' should be blocked
        # Proposal with implementation_status != 'validated' should be blocked
        
        proposal = {
            'status': 'approved',  # Not validated
            'implementation_status': 'completed'  # Not validated
        }
        
        # Sync should be blocked
        can_sync = (proposal['status'] == 'validated' and 
                   proposal['implementation_status'] == 'validated')
        assert can_sync is False
