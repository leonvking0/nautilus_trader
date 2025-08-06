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

"""Schema migration utilities for Backpack adapter."""

import json
from pathlib import Path
from typing import Any, TypeVar

import msgspec

from nautilus_trader.adapters.backpack.schemas.versioning import (
    SCHEMA_VERSIONS,
    get_migrator,
    get_validator,
)
from nautilus_trader.common.component import Logger


T = TypeVar("T", bound=msgspec.Struct)


class SchemaConverter:
    """Converts between different schema formats and versions."""
    
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or Logger(name=self.__class__.__name__)
        self._migrator = get_migrator()
        self._validator = get_validator()
        self._encoder = msgspec.json.Encoder()
        self._decoders: dict[str, msgspec.json.Decoder] = {}
    
    def register_decoder(self, schema_name: str, decoder: msgspec.json.Decoder) -> None:
        """
        Register a decoder for a schema.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        decoder : msgspec.json.Decoder
            The msgspec decoder for the schema.
            
        """
        self._decoders[schema_name] = decoder
        self._logger.debug(f"Registered decoder for {schema_name}")
    
    def decode_with_migration(
        self,
        schema_name: str,
        data: bytes | str | dict,
        target_version: str | None = None,
    ) -> Any:
        """
        Decode data with automatic migration if needed.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        data : bytes | str | dict
            The data to decode.
        target_version : str, optional
            The target version. If None, uses the current version.
            
        Returns
        -------
        Any
            The decoded and migrated object.
            
        """
        # Convert to dict if needed
        if isinstance(data, bytes):
            data_dict = json.loads(data)
        elif isinstance(data, str):
            data_dict = json.loads(data)
        else:
            data_dict = data
        
        # Migrate if needed
        migrated_data = self._migrator.migrate(schema_name, data_dict, target_version)
        
        # Validate
        if not self._validator.validate(schema_name, migrated_data):
            self._logger.warning(f"Validation failed for {schema_name}")
        
        # Decode with appropriate decoder
        if schema_name in self._decoders:
            return self._decoders[schema_name].decode(
                self._encoder.encode(migrated_data)
            )
        
        return migrated_data
    
    def encode_with_version(self, obj: msgspec.Struct, schema_name: str) -> bytes:
        """
        Encode an object with version information.
        
        Parameters
        ----------
        obj : msgspec.Struct
            The object to encode.
        schema_name : str
            The name of the schema.
            
        Returns
        -------
        bytes
            The encoded data with version info.
            
        """
        # Convert to dict
        data_dict = msgspec.structs.asdict(obj)
        
        # Add version
        data_dict["_version"] = SCHEMA_VERSIONS.get(schema_name, "1.0.0")
        
        return self._encoder.encode(data_dict)


class SchemaBackup:
    """Handles backup and restoration of schema data."""
    
    def __init__(self, backup_dir: Path | str, logger: Logger | None = None) -> None:
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logger or Logger(name=self.__class__.__name__)
    
    def backup(self, schema_name: str, data: dict, version: str | None = None) -> Path:
        """
        Backup schema data to a file.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        data : dict
            The data to backup.
        version : str, optional
            The version to tag the backup with.
            
        Returns
        -------
        Path
            The path to the backup file.
            
        """
        version = version or SCHEMA_VERSIONS.get(schema_name, "1.0.0")
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        
        filename = f"{schema_name}_v{version}_{timestamp}.json"
        filepath = self._backup_dir / filename
        
        # Add metadata
        backup_data = {
            "schema": schema_name,
            "version": version,
            "timestamp": timestamp,
            "data": data,
        }
        
        with open(filepath, "w") as f:
            json.dump(backup_data, f, indent=2)
        
        self._logger.info(f"Backed up {schema_name} to {filepath}")
        return filepath
    
    def restore(self, filepath: Path | str, target_version: str | None = None) -> dict:
        """
        Restore schema data from a backup file.
        
        Parameters
        ----------
        filepath : Path | str
            The path to the backup file.
        target_version : str, optional
            The target version to migrate to.
            
        Returns
        -------
        dict
            The restored and optionally migrated data.
            
        """
        filepath = Path(filepath)
        
        with open(filepath) as f:
            backup_data = json.load(f)
        
        schema_name = backup_data["schema"]
        version = backup_data["version"]
        data = backup_data["data"]
        
        self._logger.info(f"Restoring {schema_name} v{version} from {filepath}")
        
        # Migrate if needed
        if target_version and target_version != version:
            migrator = get_migrator()
            data = migrator.migrate(schema_name, data, target_version)
            self._logger.info(f"Migrated {schema_name} from v{version} to v{target_version}")
        
        return data
    
    def list_backups(self, schema_name: str | None = None) -> list[Path]:
        """
        List available backup files.
        
        Parameters
        ----------
        schema_name : str, optional
            Filter by schema name.
            
        Returns
        -------
        list[Path]
            List of backup file paths.
            
        """
        if schema_name:
            pattern = f"{schema_name}_v*.json"
        else:
            pattern = "*_v*.json"
        
        return sorted(self._backup_dir.glob(pattern))


class SchemaBatchProcessor:
    """Process multiple schema objects in batch with migration support."""
    
    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or Logger(name=self.__class__.__name__)
        self._converter = SchemaConverter(logger)
        self._migrator = get_migrator()
        self._validator = get_validator()
    
    def process_batch(
        self,
        schema_name: str,
        items: list[dict],
        target_version: str | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        Process a batch of items with migration and validation.
        
        Parameters
        ----------
        schema_name : str
            The name of the schema.
        items : list[dict]
            The items to process.
        target_version : str, optional
            The target version to migrate to.
            
        Returns
        -------
        tuple[list[dict], list[dict]]
            Tuple of (successful items, failed items).
            
        """
        successful = []
        failed = []
        
        for item in items:
            try:
                # Migrate
                migrated = self._migrator.migrate(schema_name, item, target_version)
                
                # Validate
                if self._validator.validate(schema_name, migrated):
                    successful.append(migrated)
                else:
                    failed.append(item)
                    self._logger.warning(f"Validation failed for item in {schema_name}")
                    
            except Exception as e:
                failed.append(item)
                self._logger.error(f"Failed to process item in {schema_name}: {e}")
        
        self._logger.info(
            f"Batch processed {schema_name}: "
            f"{len(successful)} successful, {len(failed)} failed"
        )
        
        return successful, failed
    
    def migrate_file(
        self,
        input_path: Path | str,
        output_path: Path | str,
        schema_name: str,
        target_version: str,
    ) -> None:
        """
        Migrate a file containing schema data.
        
        Parameters
        ----------
        input_path : Path | str
            The input file path.
        output_path : Path | str
            The output file path.
        schema_name : str
            The name of the schema.
        target_version : str
            The target version.
            
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        # Read input
        with open(input_path) as f:
            data = json.load(f)
        
        # Handle single item or list
        if isinstance(data, list):
            successful, failed = self.process_batch(schema_name, data, target_version)
            output_data = successful
            
            if failed:
                # Save failed items separately
                failed_path = output_path.parent / f"{output_path.stem}_failed.json"
                with open(failed_path, "w") as f:
                    json.dump(failed, f, indent=2)
                self._logger.warning(f"Failed items saved to {failed_path}")
        else:
            output_data = self._migrator.migrate(schema_name, data, target_version)
        
        # Write output
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        
        self._logger.info(f"Migrated {input_path} to {output_path}")


# Convenience functions
def migrate_schema(
    schema_name: str,
    data: dict,
    target_version: str | None = None,
) -> dict:
    """
    Convenience function to migrate schema data.
    
    Parameters
    ----------
    schema_name : str
        The name of the schema.
    data : dict
        The data to migrate.
    target_version : str, optional
        The target version.
        
    Returns
    -------
    dict
        The migrated data.
        
    """
    return get_migrator().migrate(schema_name, data, target_version)


def validate_schema(schema_name: str, data: dict) -> bool:
    """
    Convenience function to validate schema data.
    
    Parameters
    ----------
    schema_name : str
        The name of the schema.
    data : dict
        The data to validate.
        
    Returns
    -------
    bool
        True if valid, False otherwise.
        
    """
    return get_validator().validate(schema_name, data)


# Import pandas only if needed for timestamp
try:
    import pandas as pd
except ImportError:
    # Use datetime if pandas not available
    import datetime
    
    class pd:
        class Timestamp:
            @staticmethod
            def now():
                return datetime.datetime.now()