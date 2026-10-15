package com.pokecollector.app.data.db

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Delete
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

/** One line in the collection: a card in a particular print variant, with a count. */
@Entity(tableName = "collection")
data class OwnedCard(
    @PrimaryKey(autoGenerate = true) val rowId: Long = 0,
    val cardId: String,
    val name: String,
    val number: String,
    val setName: String,
    val setTotal: Int,
    val rarity: String?,
    val imageSmall: String,
    val imageLarge: String,
    val variant: String,
    val quantity: Int,
    /** Latest known market value per copy, USD. */
    val priceUsd: Double?,
    /** Cardmarket trend per copy, EUR. */
    val priceEur: Double?,
    val tcgplayerUrl: String?,
    val priceUpdatedAt: Long,
    val addedAt: Long,
)

@Dao
interface CollectionDao {
    @Query("SELECT * FROM collection ORDER BY addedAt DESC")
    fun observeAll(): Flow<List<OwnedCard>>

    @Query("SELECT * FROM collection")
    suspend fun all(): List<OwnedCard>

    @Query("SELECT * FROM collection WHERE rowId = :rowId")
    fun observe(rowId: Long): Flow<OwnedCard?>

    @Query("SELECT * FROM collection WHERE cardId = :cardId AND variant = :variant LIMIT 1")
    suspend fun find(cardId: String, variant: String): OwnedCard?

    @Insert
    suspend fun insert(card: OwnedCard): Long

    @Update
    suspend fun update(card: OwnedCard)

    @Delete
    suspend fun delete(card: OwnedCard)
}

@Database(entities = [OwnedCard::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun collection(): CollectionDao

    companion object {
        fun create(context: Context): AppDatabase =
            Room.databaseBuilder(context, AppDatabase::class.java, "collection.db").build()
    }
}
