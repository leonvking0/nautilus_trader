# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""Schema versioning and migration support for Backpack adapter."""

from typing import Any, Callable, TypeVar

import msgspec

from nautilus_trader.common.component import Logger


# Current schema versions
SCHEMA_VERSIONS = {
    "BackpackMarket": "1.0.0",
    "BackpackTicker": "1.0.0",
    "BackpackOrderBook": "1.0.0",
    "BackpackTrade": "1.0.0",
    "BackpackAccount": "1.0.0",
    "BackpackBalance": "1.0.0",
    "BackpackOrder": "1.0.0",
    "BackpackPosition": "1.0.0",
}

T = TypeVar("T", bound=msgspec.Struct)


class SchemaVersion(msgspec.Struct):
    """Base class for versioned schemas."""
    
    _version: str = "1.0.0"
    
    @classmethod
    def get_version(cls) -> str:
        """Get the schema version."""
        return cls._version


class SchemaMigration:
    """Handles schema migration between versions."""
    
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or Logger(name=self.__class__.__name__)
        self._migrations: dict[tuple[str, str, str], Callable] = {}
        
    def register_migration(
        self,
        schema_name: str,
        from_version: str,
        to_version: str,
        migration_func: Callable[[dict], dict],
    ) -> None:
        """
        Register a migration function for a schema.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        from_version : str
            The source version.
        to_version : str
            The target version.
        migration_func : Callable[[dict], dict]
            The migration function that transforms the data.
            
        """
        key = (schema_name, from_version, to_version)
        self._migrations[key] = migration_func
        self._logger.debug(f"Registered migration {schema_name} {from_version} -> {to_version}")
    
    def migrate(
        self,
        schema_name: str,
        data: dict[str, Any],
        target_version: str | None = None,
    ) -> dict[str, Any]:
        """
        Migrate data to the target schema version.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        data : dict[str, Any]
            The data to migrate.
        target_version : str, optional
            The target version. If None, uses the current version.
            
        Returns
        -------
        dict[str, Any]
            The migrated data.
            
        """
        # Get source version from data or assume 1.0.0
        source_version = data.get("_version", "1.0.0")
        
        # Use current version if target not specified
        if target_version is None:
            target_version = SCHEMA_VERSIONS.get(schema_name, "1.0.0")
        
        # No migration needed if versions match
        if source_version == target_version:
            return data
        
        # Check if direct migration exists
        key = (schema_name, source_version, target_version)
        if key in self._migrations:
            self._logger.debug(f"Migrating {schema_name} {source_version} -> {target_version}")
            return self._migrations[key](data)
        
        # Try to find a migration path
        migrated_data = data
        current_version = source_version
        
        # Simple linear migration path (can be enhanced with graph traversal)
        while current_version != target_version:
            migration_found = False
            
            for (name, from_ver, to_ver), func in self._migrations.items():
                if name == schema_name and from_ver == current_version:
                    self._logger.debug(f"Migrating {schema_name} {from_ver} -> {to_ver}")
                    migrated_data = func(migrated_data)
                    current_version = to_ver
                    migration_found = True
                    break
            
            if not migration_found:
                self._logger.warning(
                    f"No migration path found for {schema_name} "
                    f"{source_version} -> {target_version}"
                )
                return data
        
        return migrated_data


class SchemaValidator:
    """Validates schema compatibility and data integrity."""
    
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or Logger(name=self.__class__.__name__)
        self._validators: dict[str, Callable[[dict], bool]] = {}
    
    def register_validator(
        self,
        schema_name: str,
        validator_func: Callable[[dict], bool],
    ) -> None:
        """
        Register a validator function for a schema.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        validator_func : Callable[[dict], bool]
            The validation function.
            
        """
        self._validators[schema_name] = validator_func
        self._logger.debug(f"Registered validator for {schema_name}")
    
    def validate(self, schema_name: str, data: dict[str, Any]) -> bool:
        """
        Validate data against a schema.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        data : dict[str, Any]
            The data to validate.
            
        Returns
        -------
        bool
            True if valid, False otherwise.
            
        """
        if schema_name not in self._validators:
            self._logger.warning(f"No validator registered for {schema_name}")
            return True
        
        try:
            return self._validators[schema_name](data)
        except Exception as e:
            self._logger.error(f"Validation failed for {schema_name}: {e}")
            return False


# Global instances
_migrator = SchemaMigration()
_validator = SchemaValidator()


def get_migrator() -> SchemaMigration:
    """Get the global schema migrator instance."""
    return _migrator


def get_validator() -> SchemaValidator:
    """Get the global schema validator instance."""
    return _validator


# Example migrations (to be populated as schema evolves)
def _migrate_market_1_0_to_1_1(data: dict) -> dict:
    """Example migration for BackpackMarket from 1.0.0 to 1.1.0."""
    # Example: Add new field with default value
    data["_version"] = "1.1.0"
    if "settlement_currency" not in data:
        data["settlement_currency"] = data.get("quote_currency", "USDC")
    return data


def _migrate_order_1_0_to_1_1(data: dict) -> dict:
    """Example migration for BackpackOrder from 1.0.0 to 1.1.0."""
    # Example: Rename field
    data["_version"] = "1.1.0"
    if "order_type" in data and "type" not in data:
        data["type"] = data.pop("order_type")
    return data


# Register example migrations (uncomment when needed)
# _migrator.register_migration("BackpackMarket", "1.0.0", "1.1.0", _migrate_market_1_0_to_1_1)
# _migrator.register_migration("BackpackOrder", "1.0.0", "1.1.0", _migrate_order_1_0_to_1_1)


# Example validators
def _validate_market(data: dict) -> bool:
    """Validate BackpackMarket data."""
    required_fields = [
        "symbol", "base_currency", "quote_currency",
        "price_decimals", "quantity_decimals"
    ]
    return all(field in data for field in required_fields)


def _validate_order(data: dict) -> bool:
    """Validate BackpackOrder data."""
    required_fields = ["id", "symbol", "side", "order_type", "status"]
    if not all(field in data for field in required_fields):
        return False
    
    # Additional validation
    if data.get("side") not in ["buy", "sell", "BUY", "SELL"]:
        return False
    
    return True


# Register validators
_validator.register_validator("BackpackMarket", _validate_market)
_validator.register_validator("BackpackOrder", _validate_order)